// MorphRig - frame time and hardware logger for the showcase client.
//
// The actor measures the real frame time of the packaged client, keeps a
// rolling window and writes one CSV row per second plus a machine summary
// (CPU, RAM, GPU).  The HUD reads the live numbers from it.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MorphRigPerfLogger.generated.h"

/**
 * Per frame timings of the parts of the frame that the showcase drives.
 *
 * The subsystems fill in their own cost while they run, the logger reads the
 * result when it writes a row.  That shows where the frame time is spent
 * instead of only how long the frame took.
 */
struct FMorphRigFrameBreakdown
{
	/** Time the game thread spent on the frame, in milliseconds. */
	double GameThread = 0.0;

	/** Time the render thread spent on the frame, in milliseconds. */
	double RenderThread = 0.0;

	/** GPU frame time, in milliseconds. */
	double Gpu = 0.0;

	/** Time the HUD spent drawing its text, in milliseconds. */
	double Hud = 0.0;

	/** Time the operative spent in its own tick, in milliseconds. */
	double Character = 0.0;

	/** Time the animation instance spent updating, in milliseconds. */
	double Animation = 0.0;

	/** The breakdown of the frame that is currently running. */
	static FMorphRigFrameBreakdown& Current()
	{
		static FMorphRigFrameBreakdown Breakdown;
		return Breakdown;
	}
};

/** One aggregated second of frame times. */
USTRUCT(BlueprintType)
struct FMorphRigFrameSample
{
	GENERATED_BODY()

	/** Seconds since the logger started. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	double Time = 0.0;

	/** Number of frames in the sample. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	int32 Frames = 0;

	/** Average frame time in milliseconds. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float AverageMs = 0.0f;

	/** Slowest frame of the sample in milliseconds. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float MaxMs = 0.0f;

	/** Fastest frame of the sample in milliseconds. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float MinMs = 0.0f;

	/** 99th percentile frame time in milliseconds. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float P99Ms = 0.0f;

	/** Frames per second of this sample. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float Fps = 0.0f;

	/** Physical memory in use in megabytes. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float RamUsedMb = 0.0f;
};

/**
 * Measures the frame time of the running client and writes the results to
 * <Project>/Saved/Logs/MorphRigPerf.csv.
 */
UCLASS()
class MORPHRIG_API AMorphRigPerfLogger : public AActor
{
	GENERATED_BODY()

public:
	AMorphRigPerfLogger();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/** The most recent aggregated second. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	const FMorphRigFrameSample& GetLastSample() const { return LastSample; }

	/** Smoothed frames per second. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetAverageFps() const { return AverageFps; }

	/** Average frame time of the whole run in milliseconds. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetAverageFrameMs() const { return TotalFrames > 0 ? TotalTimeMs / TotalFrames : 0.0f; }

	/** The worst 99th percentile frame time seen so far. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetWorstP99Ms() const { return WorstP99Ms; }

	/** Absolute path of the CSV file that is written. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	FString GetCsvPath() const { return CsvPath; }

	/** A human readable description of the machine. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static FString GetHardwareSummary();

private:
	void WriteHeader();
	void WriteSample(const FMorphRigFrameSample& Sample);

	/** Frame times of the current sample, in milliseconds. */
	TArray<float> FrameTimes;

	double StartTime = 0.0;
	double SampleStart = 0.0;
	double LastTickTime = 0.0;
	double TotalTimeMs = 0.0;
	float AutoQuitSeconds = 0.0f;
	int64 TotalFrames = 0;
	float AverageFps = 0.0f;
	float WorstP99Ms = 0.0f;
	FMorphRigFrameSample LastSample;
	FString CsvPath;
	FArchive* CsvFile = nullptr;
};
