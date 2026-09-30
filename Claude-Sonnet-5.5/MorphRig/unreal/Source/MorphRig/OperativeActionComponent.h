// MORPHRIG: state machine, clip timelines and event dispatch of the Operative (the controller of the animation contract).
// The component runs on the game thread inside the movement tick (before movement and before the mesh evaluates), decides
// which clips play, fires the manifest events exactly once per pass and writes the FOperativePoseRecipe that the anim proxy renders.
// Rules: docs/animation_state_contract.md.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OperativeTypes.h"
#include "OperativeActionComponent.generated.h"

class UOperativeLibrary;
class AOperativeCharacter;
class UOperativeFaceComponent;

/** Timeline of one clip with once per pass event dispatch. */
struct FOperativePlayer
{
	FName ClipId;
	const FOperativeClipInfo* Info = nullptr;
	float Time = 0.f;             // clip seconds
	float Length = 0.f;
	float Rate = 1.f;
	bool bLoop = false;
	bool bActive = false;
	bool bFinished = false;
	bool bPaused = false;
	int32 NextEvent = 0;
	int32 PassId = 0;
	FName Role;                   // base, upper, hit0, hit1
	const TArray<FOperativeEventDef>* Events = nullptr;

	float Normalized() const { return Length > 1e-4f ? Time / Length : 0.f; }
	void Reset() { *this = FOperativePlayer(); }
};

UCLASS(ClassGroup = (Operative), meta = (BlueprintSpawnableComponent))
class MORPHRIG_API UOperativeActionComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UOperativeActionComponent();

	virtual void BeginPlay() override;

	/** Main update, called by the character before movement (game thread). */
	void UpdateActions(float Dt);

	// ---------------------------------------------------------------- inputs (set every frame or when changed)
	void SetMoveInput(const FVector& WorldDir, float DesiredSpeedCmS);
	void SetAimTarget(const FVector& WorldPoint, bool bHasTarget);
	void SetAimHold(bool bHold) { bAimHold = bHold; }
	void SetLookTarget(const FVector& WorldPoint, bool bEnabled) { LookTarget = WorldPoint; bLookEnabled = bEnabled; }
	void SetFacingMode(EOperativeFacingMode Mode) { FacingMode = Mode; }
	EOperativeFacingMode GetFacingMode() const { return FacingMode; }
	void SetActionRate(float Rate) { ActionRate = FMath::Clamp(Rate, 0.5f, 1.5f); }
	float GetActionRate() const { return ActionRate; }
	void SetCombatStance(bool bCombat) { bCombatStance = bCombat; }
	void SetHealthFraction(float F) { Health = FMath::Clamp(F, 0.f, 1.f); }
	float GetHealthFraction() const { return Health; }
	void SetWoundedOverride(bool b) { bWoundedOverride = b; }
	void SetRoot(bool b) { bRooted = b; }
	void SetSilence(bool b);
	void SetDisarm(bool b);
	void SetStasis(bool b) { bStasis = b; }
	bool IsRooted() const { return bRooted; }
	bool IsSilenced() const { return bSilenced; }
	bool IsDisarmed() const { return bDisarmed; }
	bool IsStasis() const { return bStasis; }
	void SetIKEnabled(bool b) { bIKEnabled = b; }
	void SetSecondaryEnabled(bool b) { bSecondaryEnabled = b; }
	void SetAimAlways(bool b) { bAimAlways = b; }
	bool GetAimAlways() const { return bAimAlways; }

	// ---------------------------------------------------------------- commands (return true when accepted)
	bool RequestJump();
	bool RequestDash(const FVector& WorldDir);           // zero vector = forward relative to facing
	bool RequestBlink(const FVector& WorldDir, float Distance = 600.f);
	bool RequestMelee();
	bool RequestFire();
	bool RequestBurst();
	bool RequestCastDirectional();
	bool RequestCastGround();
	bool RequestCastSelf();
	bool RequestReload();
	bool RequestChannelStart();
	void RequestChannelRelease();
	bool RequestChargeStart();
	void RequestChargeRelease();
	void RequestChargeCancel();
	bool RequestDeploy();
	bool RequestUplinkStart();
	void RequestUplinkCancel();
	bool RequestEmote(EOperativeAction Which);            // Greet, Victory, Defeat
	bool RequestDialogue();
	void StopDialogue();
	/** Interrupt the running sustained action (channel, charge, uplink) or any other cancellable action. */
	void InterruptAction(EOperativeInterrupt Reason);

	/** Hit reaction. HitTravelDir is the direction the hit travels (attacker towards the victim). */
	void ApplyHit(const FVector& HitTravelDir, float Damage = 0.f);
	bool ApplyStun(float Duration);
	bool ApplySleep(float Duration);
	bool ApplyKnockback(const FVector& TravelDir, float Distance);
	bool ApplyKnockup(const FVector& TravelDir, float LaunchSpeed);
	bool ApplyKnockdown(const FVector& HitTravelDir);
	void WakeUp();
	void Kill(const FVector& HitTravelDir);
	void Respawn();
	void ResetAll();

	// ---------------------------------------------------------------- animation browser / motion viewer
	bool PlayClip(FName ClipId, float Rate = 1.f, bool bForceLoop = false, float StartTime = 0.f);
	void StopViewer();
	void SetViewerPaused(bool b);
	void SeekViewer(float Time);
	bool IsViewerActive() const { return State == EOperativeState::Viewer; }

	// ---------------------------------------------------------------- outputs to the host (character / movement)
	struct FHostOutput
	{
		bool bFacingDriven = false;     // turn in place: exact yaw
		float DrivenYaw = 0.f;
		float DesiredYaw = 0.f;         // otherwise rotate towards this yaw
		float TurnRateDegS = 720.f;
		float MoveSpeedScale = 1.f;     // 0 locks movement
		bool bBrakeToStop = false;
		bool bAllowJumpInput = true;
		bool bAirControl = true;
		bool bDashActive = false;
		FVector RootMotionWorldDelta = FVector::ZeroVector;   // dash root motion of this frame
		FVector KnockbackVelocity = FVector::ZeroVector;
		bool bKnockbackActive = false;
	};
	const FHostOutput& GetHostOutput() const { return Out; }

	const FOperativePoseRecipe& GetRecipe() const { return Recipe; }

	// ---------------------------------------------------------------- queries
	EOperativeState GetState() const { return State; }
	FString GetStateString() const;
	FName GetBaseClipId() const { return Base.ClipId; }
	float GetBaseClipTime() const { return Base.Time; }
	float GetBaseClipLength() const { return Base.Length; }
	FName GetUpperClipId() const { return Upper.bActive ? Upper.ClipId : NAME_None; }
	const FOperativePlayer& GetBasePlayer() const { return Base; }
	const FOperativePlayer& GetUpperPlayer() const { return Upper; }
	bool IsAlive() const { return State != EOperativeState::Dying && State != EOperativeState::Dead && State != EOperativeState::Respawning; }
	bool IsDead() const { return State == EOperativeState::Dead || State == EOperativeState::Dying; }
	bool IsMeleeWindowOpen() const { return bMeleeWindow; }
	int32 GetMeleeWindowSerial() const { return MeleeWindowSerial; }
	bool IsIdle() const { return State == EOperativeState::Locomotion && LocoSub == ELocoSub::Idle; }
	bool IsChannelSustained() const { return bChannelSustain; }
	bool IsUplinkActive() const { return State == EOperativeState::Action && Action == EOperativeAction::Uplink && Phase <= 1; }
	EOperativeAction GetActionKind() const { return Action; }
	int32 GetPhase() const { return Phase; }
	bool IsChargeHolding() const { return ChargeActive; }
	float GetChargeFraction() const { return FMath::Clamp(ChargeTime / ChargeFullTime, 0.f, 1.f); }
	float GetAimYaw() const { return AimYawRel; }
	float GetAimPitch() const { return AimPitchRel; }
	float GetLocomotionPhase() const { return LocoPhase; }
	int32 GetCurrentPriority() const;
	bool IsAiming() const { return AimActive; }
	EOperativeStance GetStance() const;
	bool HasControl() const;                 // player input is accepted (movement/actions)
	const TArray<FOperativeEventInfo>& GetRecentEvents() const { return RecentEvents; }
	int32 GetDuplicateEventCount() const { return DuplicateEventCount; }
	int32 GetEventCount() const { return TotalEvents; }
	const TArray<FOperativeEventDef>* GetActiveEventDefs() const { return Base.Events; }
	UOperativeLibrary* GetLibrary() const { return Library.Get(); }

	/** Gameplay hook fan-out. The character binds to this; the showcase trace and HUD bind too. */
	FOperativeEventDelegate OnEvent;

	/** Max charge time in seconds (charge_full is raised when reached). */
	float ChargeFullTime = 1.4f;
	float UplinkDuration = 3.0f;
	float StunLoopExtra = 0.f;
	float BlinkDistance = 600.f;
	float BeaconSpawnDistance = 0.f;

	// per frame IK ground data written by the character before UpdateActions
	void SetFootIK(bool bEnabled, float PelvisOffset, const FOperativeFootIK& Left, const FOperativeFootIK& Right);
	void SetTeleportedThisFrame() { ++Recipe.SecondaryResetSerial; }

private:
	enum class ELocoSub : uint8 { Idle, Start, Move, Stop, Turn, Pivot };
	enum class EAirSub : uint8 { JumpStart, JumpAir, Fall, Land, LandHeavy };
	enum class EDisableKind : uint8 { None, Stun, Sleep, Knockback, Knockup, Knockdown };

	// ---- helpers
	UOperativeLibrary* Lib() const { return Library.Get(); }
	AOperativeCharacter* Host() const;
	const TArray<FOperativeEventDef>& EventsFor(FName ClipId);
	bool StartPlayer(FOperativePlayer& P, FName ClipId, float Rate, bool bLoop, float StartTime, FName Role);
	void AdvancePlayer(FOperativePlayer& P, float Dt);
	void FireEventAt(const FOperativePlayer& P, int32 Index, float Time);
	void EmitEvent(FName Name, FName ClipId, float ClipTime, FName Role, const FString& Params, bool bSynthetic, int32 PassId);
	void HandleEvent(const FOperativeEventInfo& Info);
	void PlayBase(FName ClipId, float Rate, bool bLoop, float BlendTime, float StartTime = 0.f);
	void RequestSnapshot(float BlendTime);
	void SetState(EOperativeState NewState);
	void ClearUpper(float Fade = 0.1f);
	void CancelActionState(bool bSilent);
	void ResetProps();

	bool CanStartAction(int32 NewPriority, bool bSustainedCancel) const;
	bool CanStartUpper() const;
	bool IsGrounded() const;
	float RelativeAngleLeft(const FVector& WorldDir) const;   // degrees, left positive, relative to the facing
	FName StanceIdleClip() const;

	// ---- state updates
	void UpdateInputs(float Dt);
	void UpdateLocomotion(float Dt);
	void UpdateAirborne(float Dt);
	void UpdateDash(float Dt);
	void UpdateBlink(float Dt);
	void UpdateAction(float Dt);
	void UpdateDisable(float Dt);
	void UpdateDeath(float Dt);
	void UpdateViewer(float Dt);
	void UpdateUpper(float Dt);
	void UpdateHits(float Dt);
	void UpdateAimLook(float Dt);
	void BuildRecipe(float Dt);

	void EnterLocomotion(float BlendTime, bool bKeepPhase = false);
	void EnterAction(EOperativeAction Which, FName FirstClip, float Rate, bool bLoop, float BlendTime);
	void StartLocoMove(bool bMatchPhase, float BlendTime);
	void FinishAction(float BlendTime);
	void AddLocoSamples(FOperativePoseRecipe& R);
	void ComputeLocoBlend(float Theta, float Speed);
	void SetPlayerPhase(FOperativePlayer& P, float NewNormalized);
	FName PickLocoDominant() const;
	void EnterAirborne(bool bFromJump);
	float ComputeDesiredYaw(float Speed) const;
	void AddSingleSample(FOperativePoseRecipe& R, const FOperativePlayer& P, float Weight);
	FVector RootDelta(const FOperativeClipInfo* Info, float T0, float T1) const;
	void StartDisable(EDisableKind Kind, FName FirstClip, float Duration);
	void ToKnockdown(const FVector& HitTravelDir, float BlendTime);
	void KillInternal(const FVector& HitTravelDir);

	// ---- data
	TWeakObjectPtr<UOperativeLibrary> Library;
	TMap<FName, TUniquePtr<TArray<FOperativeEventDef>>> EventCache;

	EOperativeState State = EOperativeState::Locomotion;
	ELocoSub LocoSub = ELocoSub::Idle;
	EAirSub AirSub = EAirSub::JumpAir;
	EOperativeAction Action = EOperativeAction::None;
	EDisableKind Disable = EDisableKind::None;
	int32 Phase = 0;                       // phase within an action or disable chain

	FOperativePlayer Base;
	FOperativePlayer Upper;
	FOperativePlayer HitPlayer[2];
	float HitWeightScale[2] = {1.f, 1.f};
	EOperativeUpper UpperKind = EOperativeUpper::None;
	bool bUpperQueued = false;
	EOperativeUpper UpperQueuedKind = EOperativeUpper::None;
	float UpperAlpha = 0.f;
	float UpperTargetAlpha = 0.f;

	// inputs
	FVector MoveDir = FVector::ZeroVector;
	float DesiredSpeed = 0.f;
	FVector AimTarget = FVector::ZeroVector;
	bool bHasAimTarget = false;
	bool bAimHold = false;
	bool bAimAlways = false;
	FVector LookTarget = FVector::ZeroVector;
	bool bLookEnabled = false;
	EOperativeFacingMode FacingMode = EOperativeFacingMode::Aim;
	float ActionRate = 1.f;
	bool bCombatStance = false;
	bool bWoundedOverride = false;
	float Health = 1.f;
	bool bRooted = false, bSilenced = false, bDisarmed = false, bStasis = false;
	bool bIKEnabled = true;
	bool bSecondaryEnabled = true;

	// locomotion
	float LocoPhase = 0.f;
	float LocoSpeedSmoothed = 0.f;
	struct FLocoBlendEntry { const FOperativeClipInfo* Info = nullptr; float Weight = 0.f; };
	TArray<FLocoBlendEntry, TInlineAllocator<6>> LocoBlend;
	float LocoStrideCm = 165.f;
	float DesiredFacingYaw = 0.f;
	float CombatTimer = 0.f;
	float NotGroundedTime = 0.f;
	bool bJumpTookOff = false;
	float FootIKAlphaState = 0.f;
	float AimYawSmoothed = 0.f, AimPitchSmoothed = 0.f;
	float LocoThetaSmoothed = 0.f;
	float IdleTime = 0.f;
	float MoveInputTime = 0.f;
	float StopTimer = 0.f;
	float TurnStartYaw = 0.f, TurnTargetYaw = 0.f;
	FVector PrevMoveDir = FVector::ZeroVector;
	FName LastMoveClipDominant;
	float LastMoveClipTime = 0.f;

	// airborne
	float AirTime = 0.f;
	float MinZVel = 0.f;
	bool bJumpQueued = false;

	// dash / blink
	FVector DashWorldDir = FVector::ZeroVector;
	float DashYaw = 0.f;
	float DashPrevTime = 0.f;
	FVector BlinkDir = FVector::ZeroVector;
	float BlinkDist = 0.f;
	bool bBlinkTeleported = false;

	// actions
	bool bComboQueued = false;
	int32 ComboIndex = 0;
	bool bCancelWindow = false;
	bool bControlReturned = false;
	bool bReleaseRequested = false;
	bool bCancelRequested = false;
	bool bInterruptRequested = false;
	EOperativeInterrupt InterruptReason = EOperativeInterrupt::Manual;
	bool bMeleeWindow = false;
	int32 MeleeWindowSerial = 0;
	bool bChannelSustain = false;
	bool ChargeActive = false;
	float ChargeTime = 0.f;
	bool bChargeFullFired = false;
	float ActionTimer = 0.f;
	bool bDialogueAudio = false;

	// disables
	float DisableTimer = 0.f;
	FVector KnockTravelDir = FVector::ZeroVector;
	float KnockDistance = 0.f;
	float KnockLaunchSpeed = 0.f;
	bool bKnockLaunched = false;
	bool bKnockdownChain = false;
	bool bHitFromFront = true;
	bool bFaceDown = false;               // knockdown_front (face down)
	bool bDeathFront = true;
	bool bDeadOnce = false;
	float DeathHoldTime = 0.f;

	// aim / look
	float AimYawRel = 0.f, AimPitchRel = 0.f;
	float AimReadyAlpha = 0.f, AimOffsetAlpha = 0.f;
	float AimHoldTimer = 0.f;
	bool AimActive = false;
	float LookYaw = 0.f, LookPitch = 0.f, LookAlpha = 0.f;

	// snapshot
	int32 SnapshotSerial = 0;
	float SnapshotDuration = 0.f;
	float SnapshotElapsed = 0.f;

	// foot IK input
	bool bFootIKInput = false;
	float PelvisOffsetInput = 0.f;
	FOperativeFootIK FootInput[2];

	FHostOutput Out;
	FOperativePoseRecipe Recipe;

	TArray<FOperativeEventInfo> RecentEvents;
	int32 DuplicateEventCount = 0;
	int32 TotalEvents = 0;
	TSet<uint64> FiredKeys;               // (player pass, event index) guard, proves once-per-pass
	int32 NextPassId = 1;
	double LocalTime = 0.0;
};
