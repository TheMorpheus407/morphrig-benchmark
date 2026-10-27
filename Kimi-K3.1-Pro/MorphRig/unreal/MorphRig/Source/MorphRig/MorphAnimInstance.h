#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/BoneReference.h"
#include "MorphAnimInstance.generated.h"

class UAnimSequence;
class USkeletalMeshComponent;

UENUM()
enum class EMorphClipLayer : uint8
{
    Locomotion,
    FullBody,
    UpperBody,
    Additive,
    AimPose
};

USTRUCT()
struct FMorphClipMetadata
{
    GENERATED_BODY()

    UPROPERTY() FName Id;
    UPROPERTY() FString AssetPath;
    UPROPERTY() FString Form = TEXT("one_shot");
    UPROPERTY() EMorphClipLayer Layer = EMorphClipLayer::FullBody;
    UPROPERTY() bool bLoop = false;
    UPROPERTY() bool bPose = false;
    UPROPERTY() bool bRootMotion = false;
    UPROPERTY() double Duration = 0.0;
    UPROPERTY() int32 EventCount = 0;
};

USTRUCT()
struct FMorphRuntimeEvent
{
    GENERATED_BODY()

    UPROPERTY() FName EventName;
    UPROPERTY() FName ClipId;
    UPROPERTY() double ClipTime = 0.0;
    UPROPERTY() int32 Traversal = 0;
};

USTRUCT()
struct FMorphAnimSnapshot
{
    GENERATED_BODY()

    UPROPERTY() FName MainClip = TEXT("idle_relaxed");
    UPROPERTY() FName UpperClip;
    UPROPERTY() FName AdditiveClip;
    UPROPERTY() FName LastEvent;
    UPROPERTY() double MainTime = 0.0;
    UPROPERTY() double MainDuration = 0.0;
    UPROPERTY() double UpperTime = 0.0;
    UPROPERTY() float MainRate = 1.0f;
    UPROPERTY() float MainBlend = 1.0f;
    UPROPERTY() bool bMainComplete = false;
    UPROPERTY() bool bStasis = false;
    UPROPERTY() bool bGroundIK = true;
    UPROPERTY() bool bGroundError = false;
    UPROPERTY() int32 GroundErrorCount = 0;
    UPROPERTY() int32 PoseErrorCount = 0;
    UPROPERTY() float GroundFootErrorCm[2] = { -1.0f, -1.0f };
    UPROPERTY() float GroundFootAngleDeg[2] = { -1.0f, -1.0f };
    UPROPERTY() float GroundPelvisOffset = 0.0f;
    int32 LoadedClipCount = 0;
    UPROPERTY() int32 Traversal = 0;
};

USTRUCT()
struct FMorphGroundFoot
{
    GENERATED_BODY()

    UPROPERTY() bool bValid = false;
    UPROPERTY() FVector EffectorComponent = FVector::ZeroVector;
    UPROPERTY() FVector NormalComponent = FVector::UpVector;
    UPROPERTY() float Offset = 0.0f;
};

USTRUCT()
struct FMorphGroundData
{
    GENERATED_BODY()

    UPROPERTY() bool bEnabled = false;
    UPROPERTY() FMorphGroundFoot Feet[2];
    UPROPERTY() float PelvisOffset = 0.0f;
};

struct FMorphPlayCommand
{
    FName Id;
    FName NextId;
    EMorphClipLayer Layer = EMorphClipLayer::FullBody;
    float Fade = 0.18f;
    bool bHold = false;
};

struct FMorphClipPlayer
{
    TObjectPtr<UAnimSequence> Sequence = nullptr;
    FMorphClipMetadata Metadata;
    FName NextId;
    double Time = 0.0;
    double PreviousTime = 0.0;
    float Blend = 1.0f;
    float BlendDuration = 0.18f;
    float RateMultiplier = 1.0f;
    bool bActive = false;
    bool bComplete = false;
    bool bHold = false;
    int32 LoopIndex = 0;
    uint64 Activation = 0;
    FDeltaTimeRecord DeltaTimeRecord;

    void Reset()
    {
        Sequence = nullptr;
        Metadata = FMorphClipMetadata();
        NextId = NAME_None;
        Time = PreviousTime = 0.0;
        Blend = 1.0f;
        bActive = bComplete = bHold = false;
        LoopIndex = 0;
        Activation = 0;
        DeltaTimeRecord = FDeltaTimeRecord();
    }
};

USTRUCT()
struct FMorphRigAnimInstanceProxy : public FAnimInstanceProxy
{
    GENERATED_BODY()

    FMorphRigAnimInstanceProxy() = default;
    explicit FMorphRigAnimInstanceProxy(UAnimInstance* InInstance);

    void StartClip(const FMorphPlayCommand& Command);
    void SamplePlayer(const FMorphClipPlayer& Player, FPoseContext& OutPose, bool bFullPose = true) const;
    void ApplyProceduralBones(FCompactPose& Pose);
    void ApplyGroundIK(FCompactPose& Pose);
    void AdvancePlayer(FMorphClipPlayer& Player, float DeltaSeconds, float Rate, bool bRootMotion);
    void EmitCrossedNotifies(const FMorphClipPlayer& Player, double From, double To, bool bWrapped);
    void RebuildBoneWeights(const FBoneContainer& Bones);
    FCompactPoseBoneIndex CompactIndex(const FBoneContainer& Bones, FName BoneName);

protected:
    virtual void Initialize(UAnimInstance* InAnimInstance) override;
    virtual void InitializeObjects(UAnimInstance* InAnimInstance) override;
    virtual void ClearObjects() override;
    virtual void AddReferencedObjects(UAnimInstance* InAnimInstance, FReferenceCollector& Collector) override;
    virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
    virtual void Update(float DeltaSeconds) override;
    virtual void CacheBones() override;
    virtual bool Evaluate(FPoseContext& Output) override;
    virtual void UpdateCurvesPostEvaluation(USkeletalMeshComponent* Mesh) override;

private:
    TMap<FName, TObjectPtr<UAnimSequence>> Sequences;
    TMap<FName, FMorphClipMetadata> Inventory;
    FMorphClipPlayer Main;
    FMorphClipPlayer Previous;
    FMorphClipPlayer Upper;
    FMorphClipPlayer UpperPrevious;
    FMorphClipPlayer Hit;
    float FixedStepSeconds = 0.0f;
    float ActionRate = 1.0f;
    float LocomotionRate = 1.0f;
    float AimYaw = 0.0f;
    float AimPitch = 0.0f;
    float AimWeight = 0.0f;
    bool bAimEnabled = false;
    bool bStasis = false;
    double RuntimeSeconds = 0.0;
    uint64 NextActivation = 1;
    int32 Traversal = 0;
    FMorphGroundData Ground;
    TMap<FName, float> FaceValues;
    bool bFaceOverride = false;
    FVector2D EyeLeft = FVector2D::ZeroVector;
    FVector2D EyeRight = FVector2D::ZeroVector;
    TArray<float> UpperBoneWeights;
    TArray<float> HitBoneWeights;
    TArray<float> AimBoneWeights;
    FCompactPoseBoneIndex PelvisIndex = FCompactPoseBoneIndex(INDEX_NONE);
    FCompactPoseBoneIndex UpperLegIndices[2] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
    FCompactPoseBoneIndex LowerLegIndices[2] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
    FCompactPoseBoneIndex FootIndices[2] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
    FVector RestFootUpLocal[2] = { FVector::UpVector, FVector::UpVector };
    FCompactPoseBoneIndex EyeIndices[2] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
    FCompactPoseBoneIndex CableIndices[3] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMorphEventDelegate, const FMorphRuntimeEvent&, Event);

UCLASS()
class MORPHRIG_API UMorphAnimInstance : public UAnimInstance
{
    GENERATED_BODY()

public:
    UMorphAnimInstance();

    void LoadNativeAssets();
    bool RequestClip(FName Id, float Fade = 0.18f, FName NextId = NAME_None, bool bHold = false);
    bool RequestUpperClip(FName Id, float Fade = 0.14f);
    bool RequestHit(FName Id);
    void StopUpper(float Fade = 0.12f);
    void SetPlaybackRate(float Rate);
    void SetLocomotionRate(float Rate);
    void SetAim(float Yaw, float Pitch, bool bEnabled = true);
    void SetStasis(bool bEnabled);
    void SetGroundData(const FMorphGroundData& Data);
    void SetCaptureFixedStep(bool bEnabled);
    float GetCaptureStepSeconds() const;
    void SetFaceValue(FName MorphName, float Value);
    void SetFacePreset(FName PresetName);
    void ResetFace();
    void ClearFaceOverrides();
    void SetEyeLook(float LeftYaw, float LeftPitch, float RightYaw, float RightPitch);
    void ResetRuntime();
    FMorphAnimSnapshot GetSnapshot() const;
    UAnimSequence* GetSequence(FName Id) const;
    const TMap<FName, FMorphClipMetadata>& GetInventory() const { return Inventory; }
    bool IsManifestLoaded() const { return bManifestLoaded; }
    FString GetLastError() const;

    UPROPERTY() FMorphEventDelegate OnMorphEvent;

    static const TArray<FName>& RequiredClipIds();
    static const TArray<FName>& FacialMorphNames();
    static FMorphClipMetadata MakeDefaultMetadata(FName Id);

protected:
    virtual void NativeInitializeAnimation() override;
    virtual void NativeUpdateAnimation(float DeltaSeconds) override;
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;

private:
    friend struct FMorphRigAnimInstanceProxy;
    void QueueCommand(const FMorphPlayCommand& Command);
    void PushRuntimeEvent(const FMorphRuntimeEvent& Event);
    void ReadManifest();

    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> SequenceAssets;
    UPROPERTY() TMap<FName, FMorphClipMetadata> Inventory;
    TArray<FMorphPlayCommand> PendingCommands;
    TArray<FMorphRuntimeEvent> PendingEvents;
    FMorphAnimSnapshot GameSnapshot;
    FMorphAnimSnapshot ProxySnapshot;
    FMorphGroundData PendingGround;
    TMap<FName, float> PendingFaceValues;
    FName LastError;
    float PendingActionRate = 1.0f;
    float PendingLocomotionRate = 1.0f;
    float PendingFixedStepSeconds = 0.0f;
    float PendingAimYaw = 0.0f;
    float PendingAimPitch = 0.0f;
    float PendingEyeLeftYaw = 0.0f;
    float PendingEyeLeftPitch = 0.0f;
    float PendingEyeRightYaw = 0.0f;
    float PendingEyeRightPitch = 0.0f;
    bool bPendingAim = false;
    bool bPendingStasis = false;
    bool bPendingFaceOverride = false;
    bool bManifestLoaded = false;
    bool bInventoryLoaded = false;
    bool bResetRequested = false;
    mutable FCriticalSection RuntimeLock;
};
