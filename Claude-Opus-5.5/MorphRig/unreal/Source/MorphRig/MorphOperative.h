#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MorphClipLibrary.h"
#include "MorphOperative.generated.h"

class UMorphAnimInstance;
class USpringArmComponent;
class UCameraComponent;
class UAudioComponent;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;

UENUM()
enum class EMorphState : uint8
{
	Locomotion, Transition, Airborne, Dash, Blink, Action, Channel, Charge, Uplink, Emote, Dialogue,
	Knockback, Stun, Sleep, Knockup, Down, Dead, Respawn, Preview
};

UENUM()
enum class EMorphStance : uint8 { Relaxed, Combat, Wounded };

/** A clip playing in one of the controller's layers. */
struct FMorphSlot
{
	const FMorphClip* Clip = nullptr;
	float Time = 0.f;
	float PrevTime = 0.f;
	float Rate = 1.f;
	float Weight = 0.f;
	float Target = 1.f;
	float FadeSpeed = 8.f;        // weight per second
	bool bEvents = true;          // only the newest (primary) slot dispatches markers
	bool bLoco = false;           // locomotion blend node instead of a single clip
	bool bHoldEnd = false;        // pose/final frame held after the end
	bool Finished() const;
};

struct FMorphEventLog
{
	float GameTime = 0.f;
	FString Text;
};

UCLASS()
class MORPHRIG_API AMorphOperative : public ACharacter
{
	GENERATED_BODY()

public:
	AMorphOperative();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void Landed(const FHitResult& Hit) override;

	// ------------------------------------------------------------------ commands (input, sequence, AI)
	void SetMoveInput(const FVector2D& InWorldDir, float InSpeedScale);   // world XY direction, 0..1
	void SetSprint(bool b) { bSprint = b; }
	void SetStrafe(bool b) { bStrafe = b; }
	bool IsStrafe() const { return bStrafe; }
	void SetAimInput(bool bAiming, const FVector& WorldTarget);
	void SetStance(EMorphStance S) { Stance = S; }
	EMorphStance GetStance() const { return Stance; }
	void CmdJump();
	void CmdDash();
	void CmdBlink();
	void CmdMelee();
	void CmdFire(bool bBurst);
	void CmdReload();
	void CmdCast(int32 Kind);            // 0 directional, 1 ground, 2 self
	void CmdChannel(bool bPressed);      // hold to sustain
	void CmdChannelInterrupt();
	void CmdCharge(bool bPressed);       // release fires
	void CmdChargeCancel();
	void CmdDeploy();
	void CmdUplink(bool bPressed);
	void CmdHit(int32 Dir = -1);         // 0 f, 1 b, 2 l, 3 r, -1 cycle
	void CmdStun();
	void CmdKnockback();
	void CmdKnockup();
	void CmdKnockdown(bool bFromFront);
	void CmdSleep();
	void CmdDeath(bool bFromFront);
	void CmdRespawn();
	void CmdEmote(FName Clip);
	void CmdDialogue();
	void CmdPreview(FName Clip, bool bLoopPreview);
	void CmdResume();
	void CmdResetCharacter();
	void SetRateScale(float S) { RateScale = FMath::Clamp(S, 0.5f, 1.5f); }

	// ------------------------------------------------------------------ presentation
	void SetTeam(int32 InTeam);
	int32 GetTeam() const { return Team; }
	void SetForcedLOD(int32 Lod);
	int32 GetForcedLOD() const { return ForcedLOD; }
	void SetOutline(bool b);
	bool GetOutline() const { return bOutline; }
	void SetFaceMorph(FName Name, float Value);
	void SetFaceControl(FName Ctl, float Value);   // ctl_* additive poses (lids, jaw, gaze, tongue)
	void ClearFace();
	float GetFaceMorph(FName Name) const;
	float GetFaceControl(FName Ctl) const;
	void SetFacePanelActive(bool b) { bFacePanel = b; }
	void SetAutoPilot(bool b, int32 Seed);

	// ------------------------------------------------------------------ inspection (HUD / trace)
	EMorphState GetState() const { return State; }
	FString StateName() const;
	FString CurrentClipName() const;
	float CurrentClipTime() const;
	float CurrentClipLength() const;
	float GetSpeedCms() const { return GetVelocity().Size2D(); }
	float GetRateScale() const { return RateScale; }
	const TArray<FMorphEventLog>& GetEventLog() const { return EventLog; }
	const UMorphClipLibrary* GetLibrary() const { return Library; }
	void SetLibrary(UMorphClipLibrary* Lib) { Library = Lib; }
	int32 GetEventCount() const { return EventCount; }
	FString DescribeLayers() const;
	static const TArray<FName>& MorphNames();
	static const TArray<FName>& ControlNames();

	DECLARE_MULTICAST_DELEGATE_TwoParams(FOnMorphTrace, AMorphOperative*, const FString&);
	FOnMorphTrace OnTrace;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UAudioComponent> Voice;

private:
	// controller core
	void TickController(float Dt);
	void TickLocomotion(float Dt);
	void TickState(float Dt);
	void TickSlots(TArray<FMorphSlot>& Slots, float Dt, bool bFire);
	void TickRootMotion(float Dt);
	void TickFootIK(float Dt);
	void TickLookAt(float Dt);
	void BuildRequest();
	void FillLocomotion(TArray<struct FMorphTrack, TInlineAllocator<8>>& Out, float Weight) const;
	void PlayFull(FName Id, float Blend = 0.2f, float Rate = 1.f, bool bHold = false);
	void PlayLocomotion(float Blend = 0.25f);
	void PlayUpper(FName Id, float Blend = 0.12f);
	void StopUpper(float Blend = 0.2f);
	void PlayAdditive(FName Id, float Weight);
	void EnterState(EMorphState S, FName Clip, float Blend = 0.2f);
	bool CanEnter(EMorphState S) const;
	static int32 Priority(EMorphState S);
	FMorphSlot* Primary();
	const FMorphSlot* Primary() const;
	bool PrimaryDone(float Margin = 0.f) const;
	FName PrimaryId() const;
	void FireMarkers(const FMorphSlot& S, float From, float To);
	void OnEvent(FName Clip, FName Event);
	void Trace(const FString& Text);
	FName IdleClip() const;
	FName DirClip(const TCHAR* Prefix) const;      // dash_f/b/l/r from input
	float LocalMoveAngle() const;                  // deg, 0 forward, +90 left
	void SpawnBeaconProp();
	void ClearProps();
	void FlashEffect(FName Socket, const FLinearColor& Color, float Scale, float Life);
	void ApplyTeamToMaterials();

	UPROPERTY()
	TObjectPtr<UMorphClipLibrary> Library;
	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> MIDs;
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> FxSphere;
	UPROPERTY()
	TObjectPtr<AActor> DeployedBeacon;

	TArray<FMorphSlot> Base;
	TArray<FMorphSlot> Upper;
	TArray<FMorphSlot> Additive;
	float UpperAlpha = 0.f;
	float UpperTarget = 0.f;
	float AimAlpha = 0.f;
	float AimYaw = 0.f, AimPitch = 0.f;
	bool bAiming = false;
	FVector AimTarget = FVector::ZeroVector;

	// locomotion
	FVector2D MoveInput = FVector2D::ZeroVector;
	float SpeedScale = 0.f;
	bool bSprint = false;
	bool bStrafe = true;
	float LocoPhase = 0.f;
	float LocoWalkRun = 0.f;      // 0 walk .. 1 run
	float LocoSprint = 0.f;       // run -> sprint
	float LocoIdle = 1.f;         // 1 idle .. 0 moving
	float IdleTime = 0.f;
	float LastMoveAngle = 0.f;
	float PrevSpeed = 0.f;
	EMorphStance Stance = EMorphStance::Relaxed;

	// state machine
	EMorphState State = EMorphState::Locomotion;
	float StateTime = 0.f;
	int32 Phase = 0;              // sub-step inside a state (start / loop / end ...)
	bool bHeld = false;           // channel / charge / uplink button held
	bool bComboQueued = false;
	float AirTime = 0.f;
	bool bFromFront = true;
	float PendingYaw = 0.f;       // turn / pivot clips rotate the actor at their end
	int32 HitCycle = 0;
	float RateScale = 1.f;
	bool bDeadOnce = false;
	bool bPreviewLoop = false;

	// ik / look
	float IKAlpha = 0.f;
	float PelvisOffset = 0.f;
	float FootOffset[2] = {0.f, 0.f};
	FVector FootNormal[2] = {FVector::UpVector, FVector::UpVector};
	float LookYaw = 0.f, LookPitch = 0.f, LookAlpha = 0.f;

	// face
	TMap<FName, float> FaceMorphs;
	TMap<FName, float> FaceControls;
	bool bFacePanel = false;

	// presentation
	int32 Team = 0;
	int32 ForcedLOD = 0;
	bool bOutline = false;
	bool bBeaconHidden = false;
	float FxLife = 0.f;

	// autopilot (instances)
	bool bAutoPilot = false;
	FRandomStream Rng;
	float AutoTimer = 0.f;

	TArray<FMorphEventLog> EventLog;
	int32 EventCount = 0;
};
