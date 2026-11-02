// MorphRig - frame time and hardware logger for the showcase client.
#include "MorphRigPerfLogger.h"

#include "HAL/FileManager.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "MorphRigLog.h"
#include "RHI.h"
#include "RHIGlobals.h"
#include "RenderTimer.h"

namespace
{
	/** How often a summary row is written, in seconds. */
	constexpr double SamplePeriod = 1.0;

	/** How many frame times are kept for the percentile estimate. */
	constexpr int32 MaxFrameTimes = 4096;
}

AMorphRigPerfLogger::AMorphRigPerfLogger()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.0f;
	bReplicates = false;
}

FString AMorphRigPerfLogger::GetHardwareSummary()
{
	const FPlatformMemoryStats Stats = FPlatformMemory::GetStats();
	const double UsedMb = static_cast<double>(Stats.UsedPhysical) / (1024.0 * 1024.0);
	const double TotalMb = static_cast<double>(Stats.TotalPhysical) / (1024.0 * 1024.0);
	const double FreeMb = static_cast<double>(Stats.AvailablePhysical) / (1024.0 * 1024.0);

	FString Gpu = GRHIAdapterName;
	if (Gpu.IsEmpty())
	{
		Gpu = TEXT("unknown adapter");
	}
	const double VramMb = static_cast<double>(GRHIGlobals.GpuInfo.DedicatedVideoMemory) / (1024.0 * 1024.0);

	return FString::Printf(TEXT("cpu=%s vendor=%s cores=%d logical=%d ram_total=%.0fMB ram_used=%.0fMB ram_free=%.0fMB gpu=%s vendor_id=0x%x device_id=0x%x vram=%.0fMB"), *FPlatformMisc::GetCPUBrand(), *FPlatformMisc::GetCPUVendor(), FPlatformMisc::NumberOfCores(), FPlatformMisc::NumberOfCoresIncludingHyperthreads(), TotalMb, UsedMb, FreeMb, *Gpu, GRHIVendorId, GRHIDeviceId, VramMb);
}

void AMorphRigPerfLogger::BeginPlay()
{
	Super::BeginPlay();

	StartTime = FPlatformTime::Seconds();
	SampleStart = StartTime;

	// -MorphRigAutoQuit=SECONDS stops the client on its own, so the
	// performance run needs nobody at the keyboard.
	float AutoQuit = 0.0f;
	if (FParse::Value(FCommandLine::Get(), TEXT("MorphRigAutoQuit="), AutoQuit))
	{
		AutoQuitSeconds = FMath::Max(AutoQuit, 1.0f);
		UE_LOG(LogMorphRig, Display, TEXT("PERF_AUTOQUIT %.1f"), AutoQuitSeconds);
	}

	CsvPath = FPaths::Combine(FPaths::ProjectLogDir(), TEXT("MorphRigPerf.csv"));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(CsvPath), true);

	const FString Header = TEXT("time_s,frames,avg_ms,min_ms,max_ms,p99_ms,fps,ram_used_mb,game_ms,render_ms,gpu_ms,hud_ms,character_ms,anim_ms\n");
	CsvFile = IFileManager::Get().CreateFileWriter(*CsvPath, FILEWRITE_Append);
	if (CsvFile)
	{
		const FTCHARToUTF8 Utf8(*Header);
		CsvFile->Serialize(const_cast<char*>(Utf8.Get()), Utf8.Length());
		CsvFile->Flush();
	}
	else
	{
		UE_LOG(LogMorphRig, Warning, TEXT("PERF_CSV_WRITE_FAILED %s"), *CsvPath);
	}

	UE_LOG(LogMorphRig, Display, TEXT("PERF_MACHINE %s"), *GetHardwareSummary());
	UE_LOG(LogMorphRig, Display, TEXT("PERF_CSV %s"), *CsvPath);
}

void AMorphRigPerfLogger::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// the real frame time of the client, measured from the wall clock
	const double Now = FPlatformTime::Seconds();
	if (LastTickTime == 0.0)
	{
		LastTickTime = Now;
		return;
	}
	const float RealFrameMs = static_cast<float>((Now - LastTickTime) * 1000.0);
	LastTickTime = Now;

	if (RealFrameMs <= 0.0f || RealFrameMs > 5000.0f)
	{
		return;
	}

	FrameTimes.Add(RealFrameMs);
	if (FrameTimes.Num() > MaxFrameTimes)
	{
		FrameTimes.RemoveAt(0);
	}
	TotalTimeMs += RealFrameMs;
	++TotalFrames;

	if (Now - SampleStart < SamplePeriod)
	{
		return;
	}

	FMorphRigFrameSample Sample;
	Sample.Time = Now - StartTime;
	Sample.Frames = FrameTimes.Num();

	float Sum = 0.0f;
	Sample.MinMs = FLT_MAX;
	Sample.MaxMs = 0.0f;
	for (float Ms : FrameTimes)
	{
		Sum += Ms;
		Sample.MinMs = FMath::Min(Sample.MinMs, Ms);
		Sample.MaxMs = FMath::Max(Sample.MaxMs, Ms);
	}
	Sample.AverageMs = FrameTimes.Num() > 0 ? Sum / FrameTimes.Num() : 0.0f;

	TArray<float> Sorted = FrameTimes;
	Sorted.Sort();
	const int32 P99Index = FMath::Clamp(FMath::CeilToInt(static_cast<double>(Sorted.Num()) * 0.99) - 1, 0, FMath::Max(Sorted.Num() - 1, 0));
	Sample.P99Ms = Sorted.Num() > 0 ? Sorted[P99Index] : 0.0f;
	Sample.Fps = Sample.AverageMs > 0.0f ? 1000.0f / Sample.AverageMs : 0.0f;

	const FPlatformMemoryStats Stats = FPlatformMemory::GetStats();
	Sample.RamUsedMb = static_cast<float>(static_cast<double>(Stats.UsedPhysical) / (1024.0 * 1024.0));

	// The engine publishes the cost of the threads that made the frame.  The
	// values are written once per frame in FViewport::Draw, so they describe
	// the frame that has just been presented.
	FMorphRigFrameBreakdown& Breakdown = FMorphRigFrameBreakdown::Current();
	Breakdown.GameThread = FPlatformTime::ToMilliseconds(GGameThreadTime);
	Breakdown.RenderThread = FPlatformTime::ToMilliseconds(GRenderThreadTime);
	Breakdown.Gpu = FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());

	WorstP99Ms = FMath::Max(WorstP99Ms, Sample.P99Ms);
	AverageFps = Sample.Fps;
	LastSample = Sample;

	WriteSample(Sample);
	FrameTimes.Reset();
	SampleStart = Now;

	if (AutoQuitSeconds > 0.0f && (Now - StartTime) >= AutoQuitSeconds)
	{
		UE_LOG(LogMorphRig, Display, TEXT("PERF_AUTOQUIT_REACHED"));
		FPlatformMisc::RequestExit(false);
	}
}

void AMorphRigPerfLogger::WriteSample(const FMorphRigFrameSample& Sample)
{
	const FMorphRigFrameBreakdown& Breakdown = FMorphRigFrameBreakdown::Current();

	const FString Row = FString::Printf(TEXT("%.3f,%d,%.3f,%.3f,%.3f,%.3f,%.2f,%.1f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n"),
		Sample.Time, Sample.Frames, Sample.AverageMs, Sample.MinMs, Sample.MaxMs,
		Sample.P99Ms, Sample.Fps, Sample.RamUsedMb,
		Breakdown.GameThread, Breakdown.RenderThread, Breakdown.Gpu,
		Breakdown.Hud, Breakdown.Character, Breakdown.Animation);

	UE_LOG(LogMorphRig, Display, TEXT("PERF_SAMPLE time=%.2fs frames=%d avg=%.3fms min=%.3fms max=%.3fms p99=%.3fms fps=%.2f ram=%.0fMB game=%.2fms render=%.2fms gpu=%.2fms hud=%.2fms char=%.2fms anim=%.2fms"),
		Sample.Time, Sample.Frames, Sample.AverageMs, Sample.MinMs, Sample.MaxMs,
		Sample.P99Ms, Sample.Fps, Sample.RamUsedMb,
		Breakdown.GameThread, Breakdown.RenderThread, Breakdown.Gpu,
		Breakdown.Hud, Breakdown.Character, Breakdown.Animation);

	if (CsvFile)
	{
		const FTCHARToUTF8 Utf8(*Row);
		CsvFile->Serialize(const_cast<char*>(Utf8.Get()), Utf8.Length());
		CsvFile->Flush();
	}
}

void AMorphRigPerfLogger::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (CsvFile)
	{
		CsvFile->Close();
		delete CsvFile;
		CsvFile = nullptr;
	}

	const float AverageMs = GetAverageFrameMs();
	const float RunFps = AverageMs > 0.0f ? 1000.0f / AverageMs : 0.0f;
	const FMorphRigFrameBreakdown& Breakdown = FMorphRigFrameBreakdown::Current();
	UE_LOG(LogMorphRig, Display, TEXT("PERF_SUMMARY frames=%lld total=%.2fs average=%.3fms fps=%.2f worst_p99=%.3fms game=%.2fms render=%.2fms gpu=%.2fms hud=%.2fms char=%.2fms anim=%.2fms"), TotalFrames, TotalTimeMs / 1000.0, AverageMs, RunFps, WorstP99Ms, Breakdown.GameThread, Breakdown.RenderThread, Breakdown.Gpu, Breakdown.Hud, Breakdown.Character, Breakdown.Animation);
	UE_LOG(LogMorphRig, Display, TEXT("PERF_MACHINE %s"), *GetHardwareSummary());

	Super::EndPlay(EndPlayReason);
}
