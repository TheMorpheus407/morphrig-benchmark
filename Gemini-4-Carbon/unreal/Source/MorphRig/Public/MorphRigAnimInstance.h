#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
#include "MorphRigTypes.h"
#include "MorphRigAnimInstance.generated.h"

class UMorphRigAnimInstance;

struct FMorphRigAnimInstanceProxy : public FAnimInstanceProxy
{
	FMorphRigAnimInstanceProxy() = default;
	explicit FMorphRigAnimInstanceProxy(UAnimInstance* InAnimInstance);

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual void CacheBones() override;
	virtual bool Evaluate(FPoseContext& Output) override;
	virtual void PostEvaluate(UAnimInstance* InAnimInstance) override;

	// Cached sequence lookup copied from UAnimInstance
	TMap<FName, UAnimSequence*> SequenceMap;
	TMap<FName, int32> MetaIndexMap;

	// Cached bone indices
	FCompactPoseBoneIndex RootIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex PelvisIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex Spine01Idx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex Spine02Idx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex Spine03Idx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex NeckIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex HeadIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex EyeLIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex EyeRIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex ThighLIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex CalfLIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex FootLIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex ThighRIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex CalfRIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex FootRIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex CableIdx[3] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
	FCompactPoseBoneIndex StrapIdx[3] = { FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE), FCompactPoseBoneIndex(INDEX_NONE) };
	FCompactPoseBoneIndex EmitterBoneRIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex CellBoneIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FCompactPoseBoneIndex BeaconBoneIdx = FCompactPoseBoneIndex(INDEX_NONE);
	FTransform RefCellInEmitter = FTransform::Identity;
	FTransform RefBeaconInPelvis = FTransform::Identity;
	TBitArray<> UpperBodyMask;
	FVector RefRootScale = FVector(100.0f, 100.0f, 100.0f);
	FVector MeshForwardCS = FVector(0.0f, 1.0f, 0.0f);
	FVector MeshLeftCS = FVector(-1.0f, 0.0f, 0.0f);

	// Thread-safe copied frame inputs
	EMorphRigPrimaryState PrimaryState = EMorphRigPrimaryState::Locomotion;
	FName PrimaryClip = NAME_None;
	float PrimaryTime = 0.0f;
	bool bPrimaryLoop = true;
	bool bZeroRootXY = false;

	// Locomotion transition sub-clip (start_f, stop_f, turn_l90, turn_r90, pivot_l180, pivot_r180, jump_start, jump_air, fall, jump_land, land_heavy)
	FName LocoOverrideClip = NAME_None;
	float LocoOverrideTime = 0.0f;
	float LocoOverrideWeight = 0.0f;
	bool bLocoOverrideLoop = false;

	// Continuous 8-direction locomotion inputs
	float LocalVelForward = 0.0f;
	float LocalVelRight = 0.0f;
	float GroundSpeed = 0.0f;
	float GaitPhase = 0.0f;
	bool bCombatStance = true;
	bool bWounded = false;
	bool bFear = false;
	bool bCharm = false;
	bool bTaunt = false;
	bool bStasis = false;

	// Upper-body layered action
	FName UpperClip = NAME_None;
	float UpperTime = 0.0f;
	float UpperWeight = 0.0f;

	// Calibrated 9-sample Aim Grid + Look-At
	bool bEnableAim = true;
	float AimYawDeg = 0.0f;
	float AimPitchDeg = 0.0f;
	float AimWeight = 1.0f;
	bool bEnableLookAt = true;
	FVector LookAtTargetCS = FVector(0.0f, -250.0f, 165.0f);

	// Additive hit reaction layer
	FName HitClip = NAME_None;
	float HitTime = 0.0f;
	float HitWeight = 0.0f;

	// Ground adaptation IK (up to 20 deg slope, 20 cm step)
	bool bEnableGroundIK = true;
	float GroundIKWeight = 1.0f;
	float FootOffsetZ_L = 0.0f;
	float FootOffsetZ_R = 0.0f;
	float PelvisOffsetZ = 0.0f;
	FVector FootNormalCS_L = FVector::UpVector;
	FVector FootNormalCS_R = FVector::UpVector;

	// Damped secondary settle
	FVector2D CableSpringRad = FVector2D::ZeroVector;
	FVector2D StrapSpringRad = FVector2D::ZeroVector;

	// Manual facial control panel state
	FMorphRigFaceManualState FaceManual;

	// Pose-snapshot crossfade state (prevents snapping to frame 0 on arbitrary interrupts/transitions)
	bool bCaptureSnapshotThisFrame = false;
	float SnapshotAlpha = 0.0f;
	TArray<FTransform> LastEvaluatedPose;
	TMap<FName, float> LastEvaluatedCurves;
	TArray<FTransform> SnapshotPose;
	TMap<FName, float> SnapshotCurves;
	TArray<FTransform> StasisPose;
	TMap<FName, float> StasisCurves;
	bool bHasStasisPose = false;

	// Cached static 3x3 Aim Grid bone transforms (sampled once per skeleton init, zero per-frame pose allocations)
	mutable bool bAimGridCached = false;
	mutable TArray<FTransform> CachedAimCenter;
	mutable TArray<FTransform> CachedAimGrid[3][3];
	bool bPrevHadMorphCurves = false;

private:
	void SampleClipPoseAndCurves(
		FName ClipName,
		float SampleTime,
		bool bLoop,
		FPoseContext& OutPoseCtx,
		TMap<FName, float>& OutCurves,
		bool bZeroMeshRootXY = false) const;

	void EvaluateLocomotionPose(FPoseContext& OutPoseCtx, TMap<FName, float>& OutCurves) const;
	void ApplyAimGridLayer(FPoseContext& InOutPoseCtx, float YawDeg, float PitchDeg, float Weight) const;
	void ApplyAdditiveHitLayer(FPoseContext& InOutPoseCtx, FName AdditiveClip, float SampleTime, float Weight) const;
	void ApplyLookAtAndGroundIKAndSprings(FPoseContext& InOutPoseCtx) const;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FMorphRigOnMarkerFired, const FMorphRigEventRecord&, EventRecord);

UCLASS(Transient, Blueprintable)
class MORPHRIG_API UMorphRigAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	UMorphRigAnimInstance();

	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;

	// All 96 imported UAnimSequences
	UPROPERTY(Transient, BlueprintReadOnly, Category = "MorphRig")
	TMap<FName, TObjectPtr<UAnimSequence>> LoadedSequences;

	// Primary state machine properties
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|State")
	EMorphRigPrimaryState PrimaryState = EMorphRigPrimaryState::Locomotion;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|State")
	FName PrimaryClip = TEXT("idle_combat");

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|State")
	float PrimaryTime = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|State")
	float PrimaryDuration = 2.6667f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|State")
	bool bPrimaryLoop = true;

	// Locomotion transition sub-state
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Locomotion")
	FName LocoSubClip = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Locomotion")
	float LocoSubTime = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Locomotion")
	float LocoSubWeight = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Locomotion")
	bool bLocoSubLoop = false;

	// Continuous locomotion telemetry
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Locomotion")
	float LocalVelForward = 0.0f;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Locomotion")
	float LocalVelRight = 0.0f;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Locomotion")
	float GroundSpeed = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Locomotion")
	float GaitPhase = 0.0f;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Locomotion")
	bool bIsGrounded = true;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Locomotion")
	bool bCombatStance = true;

	// Soft CC & Status Flags
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bWounded = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bRooted = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bSilenced = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bDisarmed = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bFeared = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bCharmed = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bTaunted = false;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|CC")
	bool bStasis = false;

	// Upper-body layer
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|UpperBody")
	EMorphRigUpperBodyMode UpperBodyMode = EMorphRigUpperBodyMode::None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|UpperBody")
	FName UpperClip = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|UpperBody")
	float UpperTime = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|UpperBody")
	float UpperWeight = 0.0f;

	// Aim & Look-At
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Aim")
	bool bEnableAim = true;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Aim")
	float AimYawDeg = 0.0f;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Aim")
	float AimPitchDeg = 0.0f;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Aim")
	bool bEnableLookAt = true;

	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Aim")
	FVector LookAtTargetWorld = FVector(280.0f, 0.0f, 155.0f);

	// Additive Hit Layer
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Hit")
	FName HitClip = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Hit")
	float HitTime = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Hit")
	float HitWeight = 0.0f;

	// Action playback rate (0.5x to 1.5x per SPEC §9)
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Playback")
	float ActionPlayRate = 1.0f;

	// Ground IK & Secondary Spring Settle
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|IK")
	bool bEnableGroundIK = true;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|IK")
	float FootOffsetZ_L = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|IK")
	float FootOffsetZ_R = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|IK")
	float PelvisOffsetZ = 0.0f;

	FVector FootNormalCS_L = FVector::UpVector;
	FVector FootNormalCS_R = FVector::UpVector;

	FVector2D CableSpringPos = FVector2D::ZeroVector;
	FVector2D CableSpringVel = FVector2D::ZeroVector;
	FVector2D StrapSpringPos = FVector2D::ZeroVector;
	FVector2D StrapSpringVel = FVector2D::ZeroVector;
	FVector PrevActorPos = FVector::ZeroVector;
	float PrevActorYaw = 0.0f;
	bool bPrevKinematicsValid = false;

	// Manual Face Controls
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig|Face")
	FMorphRigFaceManualState FaceManual;

	// Recent deduplicated event log
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig|Events")
	TArray<FMorphRigEventRecord> RecentEvents;

	UPROPERTY(BlueprintAssignable, Category = "MorphRig|Events")
	FMorphRigOnMarkerFired OnMarkerFired;

	// Snapshot crossfade tracking
	bool bPendingSnapshotCapture = false;
	float SnapshotCrossfadeElapsed = 1.0f;
	float SnapshotCrossfadeDuration = 0.16f;

	// Melee combo chain tracking
	int32 MeleeComboIndex = 0;
	bool bMeleeQueuedNext = false;

	// Knockdown / Death front-vs-back tracking
	bool bKnockdownIsFront = true;
	bool bDeathIsFront = true;
	float SustainedHoldTimer = 0.0f;
	float SustainedAutoFinishTime = 0.0f;
	float AirborneTime = 0.0f;

	// Deduplicated marker tracking per layer
	uint64 PrimaryInstanceCounter = 1;
	uint64 FiredPrimaryMask = 0;
	int32 PrimaryLoopIndex = 0;

	uint64 UpperInstanceCounter = 1;
	uint64 FiredUpperMask = 0;

	uint64 LocoSubInstanceCounter = 1;
	uint64 FiredLocoSubMask = 0;
	int32 GaitHalfCycleIndex = -1;

	// State-machine API
	static int32 GetStatePriority(EMorphRigPrimaryState State);
	float GetClipDuration(FName ClipId) const;
	bool IsClipLooping(FName ClipId) const;
	bool IsTerminalDead() const { return PrimaryState == EMorphRigPrimaryState::DeathDying || PrimaryState == EMorphRigPrimaryState::DeadHeld; }
	bool AllowsLocomotionInput() const;
	FString GetReadableStateSummary() const;

	void RequestSnapshotCrossfade(float BlendDuration = 0.16f);
	void ResetToReadyState();

	// High-level actions
	bool TriggerDash(FName DirectionSuffix); // "f", "b", "l", "r"
	bool TriggerBlink();
	bool TriggerMeleeAttack();
	bool TriggerUpperBodyAction(EMorphRigUpperBodyMode Mode);
	bool TriggerReload();
	bool TriggerCastGround();
	bool TriggerCastSelf();
	bool TriggerDeploy();
	bool TriggerSocialOrDialogue(FName ClipId); // greet, victory, defeat, dialogue

	// Sustained / Interruptible States
	bool StartChannel(float AutoCompleteAfterSec = 0.0f);
	bool FinishChannel();
	bool InterruptChannel();

	bool StartCharge();
	bool ReleaseCharge();
	bool CancelCharge();

	bool StartUplink(float AutoCompleteAfterSec = 0.0f);
	bool FinishUplink();
	bool CancelUplink();

	// Locomotion One-Shots & Jump
	bool TriggerLocoTransition(FName ClipId); // start_f, stop_f, turn_l90, turn_r90, pivot_l180, pivot_r180
	bool TriggerJump();

	// Hits, Disables, Death & Respawn
	void TriggerAdditiveHit(FName DirectionSuffix); // "f", "b", "l", "r"
	bool TriggerStun(float HoldDuration = 1.4f);
	bool TriggerSleep(float HoldDuration = 2.0f);
	bool WakeFromSleep();
	bool TriggerKnockback();
	bool TriggerKnockup(bool bLandFront = true);
	bool TriggerKnockdown(bool bFront = true, float ProneDuration = 1.2f);
	bool TriggerGetup();
	bool TriggerDeath(bool bFrontImpact = true);
	bool TriggerRespawn();

	// Direct 96-Clip Browser Inspection
	void PlayDirectClip(FName ClipId);
	void ExitDirectClipMode();

	// Root motion helper for dash_f/b/l/r (returns local Blender/Mesh XY delta in cm)
	FVector ConsumeDashRootDeltaCm(float PrevTime, float CurrTime, FName DashClipId) const;

private:
	FMorphRigAnimInstanceProxy AnimProxy;

	void SetPrimaryClipInternal(EMorphRigPrimaryState NewState, FName NewClip, bool bLoop, float CrossfadeSec = 0.16f);
	void CheckAndFireMarkers(FName ClipId, float PrevTime, float CurrTime, bool bLoop, FName LayerName, uint64& InOutFiredMask, int32& InOutLoopIdx);
	void EmitMarkerEvent(FName ClipId, FName MarkerName, FName LayerName, float ClipTime);
	void UpdateGroundIKAndSprings(float DeltaSeconds);
};
