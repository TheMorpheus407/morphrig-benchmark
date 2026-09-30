// MORPHRIG: showcase director. Owns the deterministic sequence (-ShowcaseSequence), the state/event trace (SHOWCASE_TRACE), the capture
// modes for the videos (-CaptureMode=turntable|motion|face -CaptureDir=) and the frame time log (-PerfLog=file.csv -Instances=1|10).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "OperativeTypes.h"
#include "ShowcasePlayerController.h"
#include "ShowcaseDirector.generated.h"

class AOperativeCharacter;
class AShowcaseRoom;
class UOperativeActionComponent;

UCLASS()
class MORPHRIG_API AShowcaseDirector : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseDirector();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	void StartSequence(bool bFromCommandLine = false);
	void StopSequence();
	bool IsSequenceRunning() const { return bSequenceRunning; }
	FString GetSequenceStatus() const;
	bool IsCapturing() const { return CaptureMode != ECaptureMode::None; }
	FString GetCaptureModeName() const;
	FString GetCurrentStepName() const { return StepName; }
	float GetSequenceProgress() const;

	/** Writes one trace line (log and file). */
	void Trace(const FString& Line);
	void Check(const FString& Name, bool bPass, const FString& Detail);

private:
	enum class ECaptureMode : uint8 { None, Turntable, Motion, Face };

	struct FTask
	{
		FString Label;
		float Timeout = 30.f;
		TFunction<void()> Begin;
		TFunction<bool()> Done;     // null = finished after Begin
		bool bStarted = false;
		float Elapsed = 0.f;
	};

	void ParseCommandLine();
	void BuildSequence();
	void RunContentChecks();
	void AddDo(const FString& Label, TFunction<void()> Fn);
	void AddWait(float Seconds);
	void AddWaitUntil(const FString& Label, TFunction<bool()> Pred, float Timeout);
	void AddWaitIdle(float Timeout = 8.f);
	void AddPhase(const FString& Name, EShowcaseView View);
	void TickSequence(float Dt);
	void TickTrace(float Dt);
	void TickCapture(float Dt);
	void TickPerf(float Dt);
	void TickShot();
	void BeginCapture();
	void FinishRun(const TCHAR* Reason);
	/** Flushes the trace and the queued PNG writes, then leaves the process without the engine teardown (the packaged Linux client asserts in its shutdown). */
	void QuitNow();
	void WritePerfSummary();
	void OnOperativeEvent(const FOperativeEventInfo& Info);
	void BindOperative();
	void IKBegin(const FString& Name);
	void IKEnd();
	void TickIKMeasure();

	AOperativeCharacter* Op() const;
	AShowcasePlayerController* PC() const;
	UOperativeActionComponent* Actions() const;
	AShowcaseRoom* Room() const;
	FVector Flat(const FVector& V) const { return FVector(V.X, V.Y, 0.f); }

	// ---- command line
	bool bWantSequence = false;
	bool bExitAfterSequence = false;
	ECaptureMode CaptureMode = ECaptureMode::None;
	FString CaptureDir;
	FString PerfLogPath;
	FString TraceFilePath;
	int32 InstancesArg = 0;
	int32 WarmupFrames = 240;        // frames and seconds of warm-up before sampling (both must pass)
	float WarmupSeconds = 5.f;
	int32 PerfFrames = 60000;        // sampling stops at this many frames or after PerfMaxSeconds, whichever comes first
	float PerfMaxSeconds = 20.f;
	bool bFixedStep = false;
	int32 MaxCaptureFrames = 0;
	int32 CaptureEvery = 1;
	FString SeqFrom, SeqTo;
	TMap<FString, float> ClipMaxStep;     // largest authored per frame bone step of every clip (cm), measured by RunContentChecks
	// one screenshot of any configuration: -Shot=file.png [-ShotFrame=150] [-ShotClip=melee_2 -ShotTime=0.4] (used to inspect views, LODs, teams, poses)
	FString ShotPath;
	FString ShotClip;
	int32 ShotFrame = 150;
	float ShotTime = -1.f;
	int32 ShotCounter = 0;
	bool bTracePose = false;
	int32 PhasesSeen = 0;
	bool bStopAfterNext = false;

	// ---- sequence
	TArray<FTask> Tasks;
	int32 TaskIndex = 0;
	bool bSequenceRunning = false;
	bool bSequenceFromCommandLine = false;
	FString StepName = TEXT("-");
	float SequenceTime = 0.f;
	FVector SeqMoveDir = FVector::ZeroVector;
	float SeqMoveSpeed = 0.f;
	FVector SeqAimPoint = FVector::ZeroVector;
	TMap<FString, FVector> Marks;
	TMap<FString, int32> Counters;
	TSet<FString> SeenClips;
	int32 PoseIgnoreFrames = 0;
	int32 TransitionFrames = 0;
	double DialogueStart = 0.0;
	int32 ExitCountdown = 0;
	double PerfLastWall = 0.0;
	int32 ChecksPassed = 0, ChecksTotal = 0;
	double PhaseStartTime = 0.0;

	// ---- trace
	FString LastState;
	FString LastClip;
	TArray<FString> TraceBuffer;
	float TraceFlushTimer = 0.f;
	int32 EventCounter = 0;
	bool bBoundOperative = false;
	TWeakObjectPtr<AOperativeCharacter> BoundTo;
	// pose continuity
	FVector PrevBonePos[6];
	bool bHavePrev = false;
	float StepMaxDelta = 0.f;
	FString StepMaxBone;
	float GlobalMaxDelta = 0.f;
	FString GlobalMaxWhere;
	int32 PoseSpikes = 0;

	// ---- foot IK measurement (planted feet against the ground under them)
	struct FIKRun { int32 Samples = 0; double SumAbs = 0.0; float MaxPenetration = 0.f; float MaxFloat = 0.f; float MaxPelvisOffset = 0.f; float MeanAbs() const { return Samples > 0 ? float(SumAbs / Samples) : 0.f; } };
	FString IKName;
	bool bIKMeasure = false;
	bool bIKHavePrev = false;
	FIKRun IKCurrent;
	TMap<FString, FIKRun> IKRuns;
	FVector IKPrev[2];
	FVector IKPrevBall[2];

	// ---- capture
	int32 CaptureFrame = 0;
	int32 CaptureTotalFrames = 0;
	float CaptureTime = 0.f;
	bool bCaptureStarted = false;
	int32 CaptureSettleFrames = 0;

	// ---- perf
	int32 PerfFrameIndex = 0;
	TArray<FString> PerfRows;
	TArray<float> PerfFrameMs, PerfGameMs, PerfRenderMs, PerfGpuMs;
	double PerfStartWall = 0.0;
	double PerfBeginWall = 0.0;
	FString PerfLoadStart;
	bool bPerfActive = false;
	bool bPerfDone = false;
};
