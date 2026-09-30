#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "MorphAnimInstance.generated.h"

class UAnimSequence;
struct FAnimInstanceProxy;

// This is copied to the evaluation proxy on the game thread. Asset lifetime is
// owned by the character's reflected sequence library.
struct FMorphPoseInput
{
    UAnimSequence* BaseA = nullptr;
    UAnimSequence* BaseB = nullptr;
    UAnimSequence* Body = nullptr;
    UAnimSequence* TravelTransition = nullptr;
    UAnimSequence* Upper = nullptr;
    UAnimSequence* Hit = nullptr;
    UAnimSequence* Neutral = nullptr;
    UAnimSequence* NeutralAim = nullptr;
    UAnimSequence* Aim[4] = {nullptr, nullptr, nullptr, nullptr};
    float AimWeights[4] = {1, 0, 0, 0};
    float BaseTimeA = 0, BaseTimeB = 0, DirectionAlpha = 0;
    float BodyTime = 0, UpperTime = 0, HitTime = 0;
    float TravelTransitionTime = 0, GaitReferenceSpeed = 0;
    FVector GaitActorLocation = FVector::ZeroVector;
    bool bTravelGait = false, bContactTransition = false, bUpperSnapshot = false;
    float UpperWeight = 0, HitWeight = 0, AimWeight = 0;
    float TransitionTime = 1;
    float FacingCompensation = 0;
    int32 TransitionSerial = 0;
    int32 ResetSerial = 0;
    float LookYaw = 0, LookPitch = 0;
    bool bGroundIK = false, bFaceOverride = false, bFrozen = false, bBeaconDeployed = false;
    FVector FootTarget[2] = {FVector::ZeroVector, FVector::ZeroVector};
    FVector FootNormal[2] = {FVector::UpVector, FVector::UpVector};
    float FootWeight[2] = {0, 0};
    float PelvisOffset = 0;
    TMap<FName, float> Face;
};

UCLASS(Transient, Blueprintable)
class MORPHRIG_API UMorphAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    FMorphPoseInput Input;
    // Published on the game thread after the worker finishes evaluation.
    // Inspection records the correction that was actually applied.
    float EvaluatedPelvisOffset = 0;
    float EvaluatedFootWeights[2] = {0, 0};
    float EvaluatedStanceWeights[2] = {0, 0};
    FName EvaluatedBaseId;
    float EvaluatedGaitPhase = 0;
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
    virtual void NativePostEvaluateAnimation() override;
};
