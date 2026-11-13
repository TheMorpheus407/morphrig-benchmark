#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MorphRigTypes.h"
#include "MorphRigGameMode.generated.h"

class AMorphRigCharacter;
class UStaticMesh;
class UMaterialInterface;
class UTextureRenderTarget2D;
class USceneCaptureComponent2D;

UCLASS()
class MORPHRIG_API AMorphRigGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMorphRigGameMode();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CachedCubeMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CachedCylinderMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CachedSphereMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> CachedBasicShapeMat;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	TObjectPtr<AMorphRigCharacter> PrimaryOperative;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	TArray<TObjectPtr<AMorphRigCharacter>> CrowdOperatives;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	TObjectPtr<AActor> AimTargetOrb;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	TObjectPtr<AActor> CameraRigActor;

	UPROPERTY(Transient)
	TObjectPtr<UTextureRenderTarget2D> OffscreenCaptureRT;

	UPROPERTY(Transient)
	TObjectPtr<USceneCaptureComponent2D> OffscreenCaptureComp;

	// Camera state
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Camera")
	EMorphRigCameraPreset ActiveCameraPreset = EMorphRigCameraPreset::OrbitClose;

	float OrbitYawDeg = -26.0f;
	float OrbitPitchDeg = -14.0f;
	float OrbitDistance = 305.0f;
	FVector OrbitPivotOffset = FVector(0.0f, 0.0f, 5.0f);
	float CurrentCameraFOV = 50.0f;

	// Instance count toggle (1 vs 10 simultaneous animated Operatives — SPEC §10)
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Instances")
	bool bTenOperativesActive = false;

	// Deterministic Showcase Sequence state (SPEC §10)
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Showcase")
	bool bShowcaseRunning = false;
	float ShowcaseElapsed = 0.0f;
	int32 ShowcaseStepIndex = -1;
	TArray<FString> ShowcaseTraceLines;
	bool bAutoExitAfterShowcase = false;

	// Performance Benchmark state (-BenchmarkPerf)
	bool bPerfBenchmarkMode = false;
	int32 PerfPhase = 0; // 0 = Warmup 1x, 1 = Measure 1x, 2 = Warmup 10x, 3 = Measure 10x
	int32 PerfFrameCounter = 0;
	TArray<double> PerfSamples1xMs;
	TArray<double> PerfSamples10xMs;
	double LastWallTimeSec = 0.0;

	// Offscreen Video Capture state (-CaptureVideo=turntable|motion|face -CaptureDir=...)
	FString CaptureMode;
	FString CaptureOutputDir;
	int32 CaptureFrameIndex = 0;
	int32 CaptureTotalFrames = 0;
	int32 CaptureWarmupFrames = 24;
	bool bHideHUDForCapture = false;

	// Live FPS / Frame-time readout
	float SmoothedFrameMs = 16.6f;
	float SmoothedFPS = 60.0f;

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetCameraPreset(EMorphRigCameraPreset Preset);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetTenOperativesEnabled(bool bEnableTen);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void StartDeterministicShowcase();

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void StopDeterministicShowcase();

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void MoveAimTarget(const FVector& DeltaWorld);

private:
	UFUNCTION()
	void OnPrimaryMarkerLogged(const FMorphRigEventRecord& Rec);

	void BuildShowcaseRoom();
	void UpdateCameraRig(float DeltaSeconds);
	void TickDeterministicShowcase(float DeltaSeconds);
	void WriteShowcaseTraceFile() const;
	void TickPerformanceBenchmark();
	void WritePerformanceReportFile() const;
	void TickVideoCapture(float DeltaSeconds);
	void SaveCapturedFramePNG(const FString& FilePath);
};
