#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MorphAnimInstance.h"
#include "MorphGameMode.generated.h"

class AMorphCharacter;
class AMorphRoom;
class UMorphHUD;
class ACameraActor;

struct FMorphBenchmarkSample
{
    double FrameMs = 0.0;
    float GameMs = 0.0f;
    float RenderMs = 0.0f;
    float GpuMs = 0.0f;
    uint64 UsedPhysical = 0;
    uint64 GpuMemory = 0;
};

UCLASS()
class MORPHRIG_API AMorphGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    AMorphGameMode();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    void SetInstanceCount(int32 Count);
    void ToggleControlPanel();
    AMorphRoom* GetRoom() const { return Room; }
    AMorphCharacter* GetOperative() const { return Operative; }

private:
    enum class EAutomationMode { None, Verify, Demo, Capture, Benchmark };
    void StartAutomation();
    void TickVerify(float DeltaSeconds);
    void TickExtendedVerify();
    void TickDemo(float DeltaSeconds);
    void TickCapture(float DeltaSeconds);
    void TickBenchmark(float DeltaSeconds);
    void RunDemoStep(int32 Step);
    void VerifyCheck(const FString& Name, bool bPassed, const FString& Details = TEXT(""));
    void FinishVerify();
    void FinishBenchmark();
    void UpdateCaptureCamera();
    FString SaveOutput(const FString& RelativePath, const FString& Contents) const;
    void BindAutomationEvents();
    bool bAutomationEventsBound = false;
    bool bAutomationStarted = false;

    UFUNCTION() void HandleAutomationEvent(const FMorphRuntimeEvent& Event);

    UPROPERTY() AMorphCharacter* Operative = nullptr;
    UPROPERTY() AMorphRoom* Room = nullptr;
    UPROPERTY() UMorphHUD* ControlPanel = nullptr;
    UPROPERTY() ACameraActor* CaptureCamera = nullptr;
    UPROPERTY() AActor* NativeProbeActor = nullptr;
    UPROPERTY() USkeletalMeshComponent* NativeProbeMesh = nullptr;
    bool bNativeProbe = false;
    UPROPERTY() TArray<TObjectPtr<AMorphCharacter>> AdditionalOperatives;
    EAutomationMode Automation = EAutomationMode::None;
    FString CaptureKind;
    FString DemoTrace;
    TArray<FString> VerifyClipRows;
    TArray<FString> VerifyCheckRows;
    TArray<FString> VerifyFailures;
    TArray<FMorphBenchmarkSample> BenchmarkSamples[2];
    int32 VerifyIndex = 0;
    int32 VerifyTransition = 0;
    int32 DemoStep = 0;
    int32 CaptureFrame = 0;
    int32 CaptureTotalFrames = 0;
    int32 BenchmarkPhase = 0;
    float AutomationClock = 0.0f;
    float PhaseClock = 0.0f;
    double LastFrameSeconds = 0.0;
    FVector VerifyStartLocation = FVector::ZeroVector;
    int32 VerifyMuzzleCount = 0;
    int32 VerifyLoopCount = 0;
    bool bPhaseStarted = false;
    bool bMidAction = false;
    bool bFinishing = false;
    double VerifyTimeRecord = 0.0;
    double VerifyRateRecord = 0.0;
    int32 VerifyTraversalRecord = 0;
    int32 VerifySubstep = 0;
    FQuat VerifyEyeReference[2] = { FQuat::Identity, FQuat::Identity };
    FVector VerifyBoneReference[2] = { FVector::ZeroVector, FVector::ZeroVector };
    void CaptureVerificationFrame(const FString& Name);
};
