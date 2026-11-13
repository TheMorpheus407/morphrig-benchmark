// Plain data handed from the game thread (UOperativeStateComponent) to the animation worker (FOperativeAnimProxy).
#pragma once
#include "CoreMinimal.h"

class UAnimSequence;

struct FOpClipSample
{
	const UAnimSequence* Seq = nullptr;
	float Time = 0.f;
	float Weight = 1.f;
	bool bLoop = false;
};

struct FOpHitSample
{
	const UAnimSequence* Seq = nullptr;
	float Time = 0.f;
	float Weight = 0.f;
};

/** Prop bone that must follow Holder with the transform authored in the source clip (0 = base layer clip, 1 = upper layer clip). */
struct FOpPropAttach
{
	FName Prop;
	FName Holder;
	float Weight = 1.f;
	int32 Source = 0;
};

struct FOpFaceBone
{
	FName Bone;
	bool bRotation = true;
	FQuat Quat = FQuat::Identity;
	FVector Loc = FVector::ZeroVector;
	float Value = 0.f;
};

struct FOpAimPose
{
	const UAnimSequence* Seq = nullptr;
	float YawDeg = 0.f;
	float PitchDeg = 0.f;
};

/** Static per-character configuration (changes only when assets are (re)loaded). */
struct FOperativeAnimConfig
{
	uint32 Serial = 0;
	TArray<FOpAimPose> AimPoses;
	TArray<const UAnimSequence*> HitClips;
};

struct FOperativeAnimInput
{
	uint32 FrameSerial = 0;
	float DeltaTime = 0.f;

	// ---- base layer: weighted blend of clips (locomotion set or a single state clip)
	TArray<FOpClipSample, TInlineAllocator<8>> Base;
	uint32 TransitionSerial = 0;      // bump to inertialize from the previous output pose
	float TransitionTime = 0.2f;
	float RootYawOffsetDeg = 0.f;     // turn / pivot compensation (Unreal yaw, component space)

	// ---- wounded posture overlay (upper body mask)
	FOpClipSample Overlay;
	float OverlayAlpha = 0.f;

	// ---- upper-body action layer
	TArray<FOpClipSample, TInlineAllocator<4>> Upper;
	float UpperAlpha = 0.f;

	// ---- aim offset (contract signs: yaw + = character left, pitch + = up)
	float AimYawDeg = 0.f;
	float AimPitchDeg = 0.f;
	float AimAlpha = 0.f;

	// ---- additive hit reactions
	TArray<FOpHitSample, TInlineAllocator<8>> Hits;

	// ---- look-at (component space)
	FVector LookTargetCS = FVector(0, 300, 160);
	float LookAlpha = 0.f;
	float EyeLookAlpha = 0.f;

	// ---- ground adaptation (index 0 = left, 1 = right)
	float FootOffsetZ[2] = { 0.f, 0.f };
	FVector FootNormalCS[2] = { FVector::UpVector, FVector::UpVector };
	float PelvisOffsetZ = 0.f;
	float FootIKAlpha = 0.f;

	// ---- face control layer (already resolved to per-channel totals on the game thread)
	TArray<TPair<FName, float>> MorphAdd;
	TArray<FOpFaceBone> FaceBones;

	// ---- props
	TArray<FOpPropAttach, TInlineAllocator<4>> PropAttach;
	TArray<FName, TInlineAllocator<4>> HiddenBones;

	// ---- switches
	bool bFrozen = false;             // stasis: hold the last evaluated pose
	bool bResetSecondary = false;     // teleport / respawn
	bool bSimulateSecondary = true;
	bool bProceduralBones = true;
};
