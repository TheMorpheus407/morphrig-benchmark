#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MorphShowcaseGameMode.generated.h"

class AMorphOperative;
class UMorphClipLibrary;
class SWidget;
class AStaticMeshActor;

/** One step of the deterministic showcase sequence. */
struct FMorphSeqStep
{
	float Time = 0.f;
	FString Label;
	TFunction<void(AMorphOperative*)> Do;
};

UCLASS()
class MORPHRIG_API AMorphShowcaseGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMorphShowcaseGameMode();
	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	UMorphClipLibrary* GetLibrary() const { return Library; }
	AMorphOperative* GetViewer() const { return Viewer; }
	AMorphOperative* GetPlayerOperative() const;

	// instances
	void SetInstanceCount(int32 N);
	int32 GetInstanceCount() const { return 1 + Instances.Num(); }

	// aim targets
	int32 NumTargets() const { return Targets.Num(); }
	FVector GetAimTargetLocation(int32 I) const;
	void MoveTarget(int32 I, const FVector& Delta);

	// panels
	void ToggleBrowser();
	void ToggleFacePanel();
	bool IsBrowserOpen() const { return BrowserWidget.IsValid(); }
	bool IsFacePanelOpen() const { return FaceWidget.IsValid(); }
	void PreviewClip(FName Id, bool bLoop, bool bOnViewer);

	// deterministic sequence / benchmark / capture
	void StartSequence(bool bExitWhenDone);
	void StopSequence();
	bool IsSequenceRunning() const { return bSequence; }
	FString SequenceStatus() const;
	bool IsCapturing() const { return !CaptureMode.IsEmpty(); }
	FString BenchStatus() const;
	int32 NextStance() const { return 1; }

private:
	void BuildRoom();
	AStaticMeshActor* Block(const FVector& Loc, const FVector& SizeCm, const FRotator& Rot, const TCHAR* Mesh,
	                        const TCHAR* Mat, bool bCollide = true);
	void Label(const FVector& Loc, const FString& Text, float Size = 28.f, const FRotator& Rot = FRotator(0, 180, 0));
	void BuildSequence();
	void TickSequence(float Dt);
	void TickBenchmark(float Dt);
	void TickCapture(float Dt);
	void FaceLabels();
	void FaceLights();
	void OnTrace(AMorphOperative* Who, const FString& Text);
	void WriteTraceLine(const FString& Line);
	void StartBenchmark(float Seconds, float Warmup, int32 Instances);
	void FinishBenchmark();
	void StartCapture(const FString& Mode, const FString& Dir);
	void SetFixedStep(float Dt);

	UPROPERTY()
	TObjectPtr<UMorphClipLibrary> Library;
	UPROPERTY()
	TObjectPtr<AMorphOperative> Viewer;
	UPROPERTY()
	TArray<TObjectPtr<AMorphOperative>> Instances;
	UPROPERTY()
	TArray<TObjectPtr<AStaticMeshActor>> Targets;
	UPROPERTY()
	TArray<TObjectPtr<AActor>> Labels;       // turned toward the camera every tick (readable from any view)
	UPROPERTY()
	TObjectPtr<class ADirectionalLight> Sun;  // key light, kept relative to the view direction
	UPROPERTY()
	TObjectPtr<class ADirectionalLight> Fill;

	TSharedPtr<SWidget> BrowserWidget;
	TSharedPtr<SWidget> FaceWidget;

	// sequence
	TArray<FMorphSeqStep> Steps;
	bool bSequence = false;
	bool bExitAfterSequence = false;
	float SeqTime = 0.f;
	int32 SeqIndex = 0;
	FString TracePath;
	TArray<FString> TraceLines;

	// benchmark
	bool bBench = false;
	float BenchSeconds = 30.f;
	float BenchWarmup = 5.f;
	float BenchClock = 0.f;
	TArray<float> FrameMs, GameMs, RenderMs, GpuMs;

	// capture
	FString CaptureMode;
	FString CaptureDir;
	int32 CaptureWarmup = 0;
	float TurntableBaseYaw = 0.f;
	int32 CaptureFrame = 0;
	int32 CaptureFrames = 0;
	float CaptureClock = 0.f;
	bool bExitAfterCapture = true;
};
