#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "MorphAnimInstance.generated.h"

class UAnimSequence;

/** One sampled clip contribution. Times are seconds; weights are normalised per layer. */
struct FMorphTrack
{
	const UAnimSequence* Seq = nullptr;
	float Time = 0.f;
	float Weight = 0.f;
	bool bLoop = false;
	bool bLockRoot = false;      // root-motion clips: pose root locked, motion applied to the capsule
};

/** Ground-adaptation request (component space, centimetres). Index 0 = left, 1 = right. */
struct FMorphLegIK
{
	float Alpha = 0.f;
	float PelvisOffset = 0.f;
	float FootOffset[2] = {0.f, 0.f};
	FVector GroundNormal[2] = {FVector::UpVector, FVector::UpVector};
};

/**
 * Everything the native controller evaluates in one frame.  Built on the game thread by
 * AMorphOperative (state machine + event dispatch), copied to the proxy in PreUpdate.
 */
struct FMorphPoseRequest
{
	TArray<FMorphTrack, TInlineAllocator<8>> Base;       // full-body stack (locomotion blend, crossfades)
	TArray<FMorphTrack, TInlineAllocator<4>> Upper;      // upper-body actions (masked from spine_01 up)
	float UpperAlpha = 0.f;
	TArray<FMorphTrack, TInlineAllocator<4>> Aim;        // bilinear blend of the 9 aim samples
	float AimAlpha = 0.f;
	TArray<FMorphTrack, TInlineAllocator<16>> Additive;  // hit reactions, face/gaze control poses
	TArray<TPair<FName, float>> Morphs;                  // face panel morph overrides
	float MorphAlpha = 0.f;
	FMorphLegIK LegIK;
	float LookYaw = 0.f;                                  // head/neck look-at, degrees
	float LookPitch = 0.f;
	float LookAlpha = 0.f;
};

struct FMorphAnimProxy : public FAnimInstanceProxy
{
	FMorphAnimProxy() = default;
	explicit FMorphAnimProxy(UAnimInstance* InAnimInstance) : FAnimInstanceProxy(InAnimInstance) {}

	virtual void Initialize(UAnimInstance* InAnimInstance) override;
	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

	FMorphPoseRequest Req;

private:
	void BuildMasks();
	void Sample(const FMorphTrack& T, FPoseContext& Out) const;
	void BlendStack(TConstArrayView<FMorphTrack> Tracks, FPoseContext& Out) const;
	void MaskedBlend(FPoseContext& InOut, const FPoseContext& Other, const TArray<float>& Mask, float Alpha) const;
	void ApplyLegIK(FPoseContext& Output) const;
	void ApplyLookAt(FPoseContext& Output) const;

	TArray<float> UpperMask;    // by mesh bone index
	TArray<float> AimMask;
	bool bMasksReady = false;
	int32 MeshPelvis = INDEX_NONE;
	int32 MeshThigh[2] = {INDEX_NONE, INDEX_NONE};
	int32 MeshCalf[2] = {INDEX_NONE, INDEX_NONE};
	int32 MeshFoot[2] = {INDEX_NONE, INDEX_NONE};
	int32 MeshNeck = INDEX_NONE;
	int32 MeshHead = INDEX_NONE;
};

/** Native animation controller: no AnimGraph, the proxy evaluates the request directly. */
UCLASS(Transient, NotBlueprintable)
class MORPHRIG_API UMorphAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	FMorphPoseRequest Request;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override { return new FMorphAnimProxy(this); }
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override { delete InProxy; }
};
