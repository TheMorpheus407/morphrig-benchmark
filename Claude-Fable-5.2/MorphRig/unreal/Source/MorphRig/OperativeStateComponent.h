#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "MorphRigData.h"
#include "OperativeAnimTypes.h"
#include "OperativeStateComponent.generated.h"

class AOperativeCharacter;
class UOperativeAnimInstance;
class UOperativeMovementComponent;
class UAnimSequence;

UENUM()
enum class EOpState : uint8
{
	Locomotion,
	Air,
	Action,
	Emote,
	Knockback,
	Sleep,
	Stun,
	Knockup,
	Knockdown,
	Respawn,
	Dead,
	Viewer
};

/** One activation of a clip. The cursor lives on the game thread; markers are dispatched from here exactly once. */
struct FOpClipPlay
{
	const FMorphClip* Info = nullptr;
	UAnimSequence* Seq = nullptr;
	float Time = 0.f;
	float FiredUpTo = -1.f;     // markers with time <= FiredUpTo were already handled in this pass
	float Rate = 1.f;
	bool bLoop = false;
	bool bFinished = false;
	bool bUseActionRate = false;
	int32 ActivationId = 0;
	int32 LoopCount = 0;

	bool IsValid() const { return Info != nullptr && Seq != nullptr; }
	FName Id() const { return Info ? Info->Id : NAME_None; }
	float Duration() const { return Info ? Info->Duration : 0.f; }
	void Reset() { *this = FOpClipPlay(); }
};

struct FOpEventRecord
{
	double WorldTime = 0.0;
	FName Clip;
	FName Event;
	float ClipTime = 0.f;
	int32 ActivationId = 0;
};

struct FOpHitInstance
{
	UAnimSequence* Seq = nullptr;
	const FMorphClip* Info = nullptr;
	float Time = 0.f;
	float Weight = 0.f;
	bool bLoopForViewer = false;
};

/** Per-frame intent written by the player controller or the autopilot. */
struct FOpInput
{
	FVector MoveDir = FVector::ZeroVector;   // world space, length 0..1
	bool bSprint = false;
	bool bWalk = false;
	bool bAim = false;                       // raise the emitter arm (aim stance)
	bool bHasAimPoint = false;
	FVector AimPoint = FVector::ZeroVector;  // world
	float SpeedOverride = -1.f;              // >= 0: exact desired speed in cm/s
};

DECLARE_MULTICAST_DELEGATE_ThreeParams(FOpEventDelegate, class UOperativeStateComponent*, const FOpClipPlay&, FName);

/**
 * Game-thread owner of the Operative's animation state (docs/animation_state_contract.md sections 3-8):
 * locomotion blend, base / upper clip cursors, priorities, status flags, marker dispatch, face control layer.
 * Writes one FOperativeAnimInput per tick for the native animation controller.
 */
UCLASS()
class MORPHRIG_API UOperativeStateComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UOperativeStateComponent();

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// ------------------------------------------------------------------ intent
	FOpInput Input;
	bool bStrafe = true;
	bool bWounded = false;
	bool bFootIK = true;
	bool bSimulateSecondary = true;
	bool bProceduralBones = true;
	bool bLookAt = true;
	bool bAutoBlink = true;
	float ActionRate = 1.f;

	// ------------------------------------------------------------------ commands (return false when refused by the rules)
	bool DoJump();
	bool DoDash(float DirDeg);
	bool DoBlink(const FVector& Destination);
	bool DoMelee();
	bool DoRanged(bool bBurst);
	bool DoReload();
	bool DoCast(FName Kind);                 // directional | ground | self
	bool ChannelPress();
	bool ChannelRelease();
	bool ChannelInterrupt(const TCHAR* Reason);
	bool ChargePress();
	bool ChargeRelease();
	bool ChargeCancel(const TCHAR* Reason);
	bool DoDeploy();
	bool UplinkStart();
	bool UplinkCancel(const TCHAR* Reason);
	bool DoTurn(float YawDeg);               // +90 = left, -90 = right
	bool PlayEmote(FName ClipId);
	void ApplyHit(float FromDeg, bool bHeavy);
	bool ApplyStun(float Duration);
	bool ApplySleep(float Duration);
	bool ApplyKnockback(float FromDeg);
	bool ApplyKnockup();
	bool ApplyKnockdown(bool bHitFromFront);
	bool Kill(bool bHitFromFront);
	bool Respawn(const FVector& Location, float YawDeg);
	void SetFlag(FName Flag, bool bOn, const FVector& Source = FVector::ZeroVector);   // root silence disarm stasis fear charm taunt
	bool HasFlag(FName Flag) const;
	bool ViewClip(FName ClipId);
	bool ViewReferencePose();
	bool IsViewingReferencePose() const { return State == EOpState::Viewer && !BaseClip.IsValid(); }
	void ExitViewer();
	void ResetAll();

	// viewer transport
	bool bViewerPaused = false;
	bool bViewerLoop = true;
	float ViewerRate = 1.f;
	void ViewerScrub(float NormalizedTime);

	// ------------------------------------------------------------------ face control layer
	TMap<FName, float> FaceDirect;
	TMap<FName, float> FaceVisemes;
	TMap<FName, float> FaceExpressions;
	/** Smoothed weights actually applied (about 0.1 s) so preset changes do not pop. */
	TMap<FName, float> FaceVisemesApplied;
	TMap<FName, float> FaceExpressionsApplied;
	bool bManualGaze = false;
	float GazeYawDeg = 0.f;
	float GazePitchDeg = 0.f;
	bool bLookAtCamera = false;
	FVector CameraLocation = FVector::ZeroVector;
	void ClearFace();

	// ------------------------------------------------------------------ queries
	EOpState GetState() const { return State; }
	FName GetActionTag() const { return Tag; }
	FString GetStateText() const;
	const FOpClipPlay& GetBaseClip() const { return BaseClip; }
	const FOpClipPlay& GetUpperClip() const { return UpperClip; }
	bool IsAlive() const { return State != EOpState::Dead; }
	bool IsBusy() const { return State != EOpState::Locomotion || UpperClip.IsValid(); }
	bool IsGrounded() const;
	float GetSpeed() const { return Speed; }
	float GetTravelDirDeg() const { return TravelDir; }
	float GetGaitPhase() const { return Phase; }
	float GetLocoRate() const { return LocoRate; }
	FString GetLocoText() const;
	float GetAimYaw() const { return AimYaw; }
	float GetAimPitch() const { return AimPitch; }
	float GetAimAlpha() const { return AimAlpha; }
	int32 GetAmmo() const { return Ammo; }
	float GetChargeLevel() const;
	float GetChargeReleaseLevel() const { return ChargeReleaseLevel; }
	FVector GetLookTargetWorld() const { return LookTargetWorld; }
	FName GetIdleClip() const { return IdleClip; }
	bool IsChanneling() const { return bChannelEmitting; }
	bool IsHitWindowOpen() const { return bHitWindow; }
	bool IsBeaconCarried() const { return !bBeaconDeployed; }
	FString GetFlagsText() const;
	FString GetAutoExpression() const { return AutoExpression.ToString(); }
	const TArray<FOpEventRecord>& GetEventLog() const { return EventLog; }
	int32 GetEventCount() const { return EventCounter; }
	float GetFootOffset(int32 Side) const { return FootOffset[Side]; }
	float GetPelvisOffset() const { return PelvisOffset; }
	/** Height of the foot joint above the surface below it (cm), measured from the last evaluated pose; -1 when not measured. */
	float GetFootClearance(int32 Side) const { return FootClearance[Side]; }
	double GetStateTime() const { return LocalTime; }

	FOpEventDelegate OnEvent;
	/** Human readable trace lines (state changes, events, refusals). */
	static TMulticastDelegate<void(const AActor*, const FString&)> OnTrace;

	void NotifyLanded(float ImpactSpeed);

private:
	// ---- helpers
	bool StartBase(FName ClipId, EOpState NewState, FName NewTag, float Blend = 0.2f, float StartTime = 0.f);
	bool StartUpper(FName ClipId, FName NewTag, float Blend = 0.12f);
	void ClearUpper(float Blend, const TCHAR* Why);
	void EnterLocomotion(float Blend);
	void SetState(EOpState NewState, FName NewTag);
	void Transition(float Blend);
	void Advance(FOpClipPlay& Play, float DeltaTime);
	void FireRange(FOpClipPlay& Play, float From, float To, bool bIncludeFrom);
	void Fire(FOpClipPlay& Play, const FMorphEvent& Event);
	void HandleEvent(const FOpClipPlay& Play, FName Event);
	void OnBaseFinished();
	void OnUpperFinished();
	void InterruptForDisable(const TCHAR* Why);
	void CancelSoftActions(const TCHAR* Why);
	bool CanStartAction(const TCHAR* What) const;
	bool CanControl() const;
	void Trace(const FString& Line) const;
	void Refuse(const TCHAR* What, const TCHAR* Why) const;

	void UpdateState(float Dt);
	void UpdateMovement(float Dt);
	void UpdateLocomotionBlend(float Dt);
	void UpdateAim(float Dt);
	void UpdateFace(float Dt);
	void UpdateFootIK(float Dt);
	void UpdateHits(float Dt);
	void BuildAnimInput(float Dt);
	void AddHitInstance(FName ClipId, float Weight, bool bLoopForViewer = false);
	void AddPropAttachments(const FOpClipPlay& Play, int32 Source, FOperativeAnimInput& Out) const;
	float LocalDirDeg(const FVector& WorldDir) const;
	void SetActorYaw(float Yaw);

	UPROPERTY(Transient)
	TObjectPtr<AOperativeCharacter> Char;
	UPROPERTY(Transient)
	TObjectPtr<UOperativeAnimInstance> Anim;
	UPROPERTY(Transient)
	TObjectPtr<UOperativeMovementComponent> Move;

	const FMorphRigData* Data = nullptr;

	EOpState State = EOpState::Locomotion;
	FName Tag;
	FOpClipPlay BaseClip;        // valid while a single clip owns the base layer (states other than the gait blend, or a locomotion one-shot)
	FOpClipPlay UpperClip;
	FName UpperTag;
	int32 ActivationCounter = 0;
	double LocalTime = 0.0;
	uint32 FrameSerial = 0;
	uint32 TransitionSerial = 0;
	float TransitionTime = 0.2f;

	// locomotion
	struct FGaitSet { TArray<const FMorphClip*> Clips; float Duration = 1.f; float Speed = 150.f; };
	FGaitSet Walk, Run;
	const FMorphClip* SprintClip = nullptr;
	float Speed = 0.f;
	float TravelDir = 0.f;
	float Phase = 0.f;
	float LocoRate = 1.f;
	float IdleTime = 0.f;
	FName IdleClip;
	FName DominantClip;
	FName TracedGait;
	FName TracedAimPose;
	float CombatTimer = 0.f;
	float RootYawOffset = 0.f;
	float TurnHoldTime = 0.f;
	bool bWasMoving = false;
	float TimeMoving = 0.f;
	FVector LastMoveDir = FVector::ZeroVector;
	TArray<FOpClipSample, TInlineAllocator<8>> LocoSamples;
	float SprintBlend = 0.f;

	// air
	float FallTime = 0.f;
	float LastFallSpeed = 0.f;
	float ApexZ = 0.f;
	bool bJumpLaunched = false;

	// actions
	int32 ComboStep = 0;
	bool bComboBuffered = false;
	bool bHitWindow = false;
	int32 Ammo = 12;
	bool bReloadCounted = false;
	float ChargeTime = -1.f;
	float ChargeReleaseLevel = 0.f;
	bool bChannelEmitting = false;
	float ChannelTime = 0.f;
	float UplinkTime = 0.f;
	bool bBeaconDeployed = false;
	float BeaconRestock = 0.f;
	bool bBeaconGrabbed = false;
	FVector BlinkDestination = FVector::ZeroVector;
	float AimHold = 0.f;
	FVector KnockDir = FVector::ZeroVector;
	float RecallDelay = -1.f;

	// disables
	float StunRemaining = 0.f;
	float SleepRemaining = 0.f;
	float ProneRemaining = 0.f;
	bool bProneFaceUp = true;
	TSet<FName> Flags;
	FVector FlagSource = FVector::ZeroVector;
	FName SavedMovementModeFlag;

	// layers
	TArray<FOpHitInstance> Hits;
	float AimYaw = 0.f, AimPitch = 0.f, AimAlpha = 0.f;
	float LookAlpha = 0.f, EyeAlpha = 0.f;
	FVector LookTargetWorld = FVector::ZeroVector;
	float FootOffset[2] = { 0.f, 0.f };
	FVector FootNormal[2] = { FVector::UpVector, FVector::UpVector };
	float PelvisOffset = 0.f;
	float FootClearance[2] = { -1.f, -1.f };
	float FootIKAlpha = 0.f;
	float AdditiveGate = 1.f;            // 0 while a floor-contact clip owns the body (no hit additive on planted hands)
	FVector ProfileDir = FVector::ForwardVector;   // travel direction of the running start / stop / pivot speed profile
	float ProfileScale = 1.f;
	int32 TracedProfileActivation = 0;
	float WoundedAlpha = 0.f;
	bool bResetSecondary = true;

	// face
	float BlinkTimer = 2.f;
	float BlinkPhase = -1.f;
	FName AutoExpression;
	float AutoExpressionWeight = 0.f;
	FName AutoExpressionTarget;
	float PainPulse = 0.f;
	FRandomStream Random;

	TArray<FOpEventRecord> EventLog;
	int32 EventCounter = 0;
};
