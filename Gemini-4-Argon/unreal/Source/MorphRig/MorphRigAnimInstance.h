#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
#include "MorphRigAnimInstance.generated.h"

class UMorphRigAnimInstance;

USTRUCT()
struct FMorphRigAnimInstanceProxy : public FAnimInstanceProxy
{
	GENERATED_BODY()

	FMorphRigAnimInstanceProxy() : FAnimInstanceProxy() {}
	FMorphRigAnimInstanceProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

	// Thread-safe snapshot of state copied in PreUpdate
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> CurrentBaseSeq = nullptr;
	double CurrentBaseTime = 0.0;

	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> PrevBaseSeq = nullptr;
	double PrevBaseTime = 0.0;
	float CrossfadeAlpha = 1.0f;

	// 8-way locomotion blend support
	bool bBlendLocomotion = false;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> LocoSeqA = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> LocoSeqB = nullptr;
	float LocoBlendAlpha = 0.0f;
	float LocoSpeedAlpha = 0.0f;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> IdleSeq = nullptr;
	double LocoCycleTime = 0.0;

	// Upper-body layer (spine_01 and above)
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> UpperBodySeq = nullptr;
	double UpperBodyTime = 0.0;
	float UpperBodyAlpha = 0.0f;

	// Additive hit reaction layer
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> HitAddSeq = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> HitRefSeq = nullptr;
	double HitAddTime = 0.0;
	float HitAddAlpha = 0.0f;

	// 9-point Aim Offset grid
	bool bEnableAimOffset = true;
	float AimYaw = 0.0f;   // [-90, +90]
	float AimPitch = 0.0f; // [-60, +60]
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimCenter = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimUp = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimDown = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimLeft = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimRight = nullptr;

	// Spoken dialogue facial layer
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> DialogueSeq = nullptr;
	double DialogueTime = 0.0;
	float DialogueAlpha = 0.0f;

	// Ground adaptation (20-deg slope & 20 cm steps)
	bool bEnableGroundIK = true;
	float PelvisOffsetZ = 0.0f;
	float FootOffsetZ_L = 0.0f;
	float FootOffsetZ_R = 0.0f;
	float FootPitchDeg_L = 0.0f;
	float FootPitchDeg_R = 0.0f;

	// Interactive facial & gaze overrides
	float GazeYawDeg = 0.0f;
	float GazePitchDeg = 0.0f;
	float ManualJawOpen = 0.0f;
	float ManualBlinkL = 0.0f;
	float ManualBlinkR = 0.0f;
	FName ActiveExpressionMorph = NAME_None;
	float ActiveExpressionWeight = 0.0f;
};

UCLASS(Transient, Blueprintable)
class MORPHRIG_API UMorphRigAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	UMorphRigAnimInstance();

	// Base animation playback with midpoint-safe crossfade
	void TransitionToBaseAnim(UAnimSequence* NewSeq, bool bLoop, float BlendDuration = 0.16f, double StartTime = 0.0);
	void PlayUpperBodyAnim(UAnimSequence* NewUpperSeq, float BlendWeight = 1.0f);
	void PlayAdditiveHit(UAnimSequence* HitSeq, UAnimSequence* RefIdleSeq);
	void AdvanceAnimations(float DeltaSeconds, float PlaybackRate);

	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> CurrentBaseSeq = nullptr;
	double CurrentBaseTime = 0.0;
	bool bCurrentBaseLoop = true;

	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> PrevBaseSeq = nullptr;
	double PrevBaseTime = 0.0;
	float CrossfadeElapsed = 0.16f;
	float CrossfadeDuration = 0.16f;

	// Locomotion 8-way state
	bool bBlendLocomotion = false;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> LocoSeqA = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> LocoSeqB = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> IdleSeq = nullptr;
	float LocoBlendAlpha = 0.0f;
	float LocoSpeedAlpha = 0.0f;
	double LocoCycleTime = 0.0;

	// Upper-body layer
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> UpperBodySeq = nullptr;
	double UpperBodyTime = 0.0;
	float UpperBodyAlpha = 0.0f;

	// Additive hit layer
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> HitAddSeq = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> HitRefSeq = nullptr;
	double HitAddTime = 0.0;
	float HitAddAlpha = 0.0f;

	// Aim offset references
	bool bEnableAimOffset = true;
	float AimYaw = 0.0f;
	float AimPitch = 0.0f;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimCenter = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimUp = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimDown = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimLeft = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> AimRight = nullptr;

	// Spoken dialogue facial overlay
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> DialogueSeq = nullptr;
	double DialogueTime = 0.0;
	float DialogueAlpha = 0.0f;

	// Ground adaptation
	bool bEnableGroundIK = true;
	float PelvisOffsetZ = 0.0f;
	float FootOffsetZ_L = 0.0f;
	float FootOffsetZ_R = 0.0f;
	float FootPitchDeg_L = 0.0f;
	float FootPitchDeg_R = 0.0f;

	// Facial controls
	float GazeYawDeg = 0.0f;
	float GazePitchDeg = 0.0f;
	float ManualJawOpen = 0.0f;
	float ManualBlinkL = 0.0f;
	float ManualBlinkR = 0.0f;
	FName ActiveExpressionMorph = NAME_None;
	float ActiveExpressionWeight = 0.0f;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override
	{
		return new FMorphRigAnimInstanceProxy(this);
	}

	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override
	{
		delete InProxy;
	}

	friend struct FMorphRigAnimInstanceProxy;
};
