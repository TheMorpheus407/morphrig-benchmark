// MORPHRIG: the Operative character (capsule 34 x 90 cm, mesh, props, face, action component) and its movement component.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "OperativeTypes.h"
#include "OperativeCharacter.generated.h"

class UOperativeActionComponent;
class UOperativeFaceComponent;
class UOperativeAnimInstance;
class UOperativeLibrary;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UAudioComponent;
class AOperativeCharacter;

/** Movement component: tick hook that runs the action component before movement, dash root motion and knockback as custom modes. */
UCLASS()
class MORPHRIG_API UOperativeMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()
public:
	UOperativeMovementComponent();
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual float GetMaxSpeed() const override;
	virtual FVector ScaleInputAcceleration(const FVector& InputAcceleration) const override;
	virtual float GetMaxBrakingDeceleration() const override;

	enum ECustomMode : uint8 { CustomNone = 0, CustomDash = 1, CustomKnockback = 2 };

	/** Gait speed cap (cm/s) chosen by the character input layer. */
	float GaitSpeed = 400.f;
	float MoveScale = 1.f;
	bool bBrakeHard = false;

protected:
	virtual void PhysCustom(float DeltaTime, int32 Iterations) override;
	virtual void OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode) override;
	AOperativeCharacter* GetOperative() const;
};

UENUM(BlueprintType)
enum class EOperativeTeam : uint8
{
	A,
	B
};

UCLASS()
class MORPHRIG_API AOperativeCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	AOperativeCharacter(const FObjectInitializer& ObjectInitializer);

	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UOperativeActionComponent> Actions;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UOperativeFaceComponent> Face;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMeshComponent> PowerCellComp;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMeshComponent> BeaconComp;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UAudioComponent> VoiceComp;

	// ------------------------------------------------------------------ high level input API (used by the player controller, the sequence and autopilots)
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetMoveIntent(FVector WorldDirection, float SpeedCmS);
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetAimPoint(FVector WorldPoint);
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetAimHold(bool bHold);
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetTeam(EOperativeTeam NewTeam);
	UFUNCTION(BlueprintCallable, Category = "Operative") EOperativeTeam GetTeam() const { return Team; }
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetForcedLOD(int32 Lod);   // 0 = automatic, 1..3 = LOD0..LOD2
	UFUNCTION(BlueprintCallable, Category = "Operative") int32 GetForcedLOD() const { return ForcedLOD; }
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetRenderMode(int32 Mode);  // 0 textured, 1 normals, 2 wireframe, 3 clay mesh
	UFUNCTION(BlueprintCallable, Category = "Operative") int32 GetRenderMode() const { return RenderMode; }
	UFUNCTION(BlueprintCallable, Category = "Operative") void ResetOperative(bool bMoveToSpawn = true);
	UFUNCTION(BlueprintCallable, Category = "Operative") void SetFacingYaw(float Yaw);
	float GetFacingYaw() const { return GetActorRotation().Yaw; }

	/** Team accent overlay (secondary outline) on/off. */
	void SetOutlineEnabled(bool bEnabled);
	/** Temporary suppression (face close-up): at close range the outline hull shows through the mouth opening. */
	void SetOutlineSuppressed(bool bSuppressed);
	bool IsOutlineEnabled() const { return bOutline; }

	// ------------------------------------------------------------------ host API used by the action component
	void HostJump();
	void HostBlinkTeleport(const FVector& Dir, float Distance);
	void HostSetMeshVisible(bool bVisible);
	void HostLaunch(const FVector& Velocity);
	void HostSpawnBeacon();
	void HostRecallBeacon();
	void HostPlayDialogue();
	void HostStopDialogue();
	void HostOnDeath();
	void HostOnRespawn();
	void HostResetProps();
	FVector GetAimOrigin() const;
	/** Grounded for the state machine: walking, or in a custom ground mode (dash, knockback) standing on a walkable floor. */
	bool IsGroundedForActions() const;
	FVector GetMuzzleLocation() const;
	FVector GetMuzzleDirection() const;
	bool GetSocketTransformSafe(FName Socket, FTransform& Out) const;

	// ------------------------------------------------------------------ gameplay hooks (events map to these, see the contract)
	void OnOperativeEvent(const FOperativeEventInfo& Info);
	/** Hits of aim targets by hitscan, blade sweep etc. report here (bound by the showcase). */
	DECLARE_MULTICAST_DELEGATE_TwoParams(FHookHit, const FVector& /*Location*/, AActor* /*Target*/);
	FHookHit OnMuzzleHit;
	FHookHit OnBladeHit;

	// ------------------------------------------------------------------ queries and debug
	UOperativeAnimInstance* GetOperativeAnim() const;
	bool IsMeshVisible() const { return bMeshVisible; }
	bool IsBeaconDeployed() const { return WorldBeacon.IsValid(); }
	FVector GetWorldBeaconLocation() const;
	int32 GetShotsFired() const { return ShotsFired; }
	int32 GetBladeHits() const { return BladeHitsTotal; }
	float GetTravelSinceReset() const { return TravelSinceReset; }
	FVector GetSpawnLocation() const { return SpawnLocation; }
	void SetSpawnTransform(const FTransform& T) { SpawnLocation = T.GetLocation(); SpawnYaw = T.Rotator().Yaw; }
	double GetDialogueAudioStartTime() const { return DialogueAudioStartTime; }
	FVector GetLastAimPoint() const { return LastAimPoint; }

	// tuning (also exposed in the docs)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Operative") float JumpVelocity = 620.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Operative") float FootIKMaxOffset = 28.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Operative") bool bAutopilot = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Operative") int32 AutopilotSeed = 1;

	/** Called by the movement component before movement. */
	void PreMovementTick(float Dt);

	FVector DesiredMoveDir = FVector::ZeroVector;
	float DesiredMoveSpeed = 0.f;

	// mesh smoothing offset for the capsule snap of steps (visual only, decays to 0)
	float MeshZSmoothOffset = 0.f;

private:
	void ApplyAssets();
	void ApplyTeamMaterials();
	void ApplyRenderMaterials();
	void UpdateFacing(float Dt);
	void UpdateFootIK(float Dt);
	void UpdateMeshSmoothing(float Dt);
	void UpdateMeleeSweep(float Dt);
	void SpawnTracer(const FVector& From, const FVector& To, const FLinearColor& Color, float Life, float Thickness);
	void PulseFx(const FVector& At, const FLinearColor& Color, float Radius, float Life);
	void UpdateFx(float Dt);
	void TickAutopilot(float Dt);
	void HandleMuzzleFire(int32 Index);
	void ResetFx();

	EOperativeTeam Team = EOperativeTeam::A;
	int32 ForcedLOD = 0;
	int32 RenderMode = 0;
	bool bOutline = true;
	bool bOutlineSuppressed = false;
	bool bMeshVisible = true;
	bool bAssetsApplied = false;
	bool bBeaconAttachedVisible = true;
	float BeaconSettleTimer = 0.f;
	FTransform BeaconSpawnTransform;
	double DialogueAudioStartTime = 0.0;
	FVector LastAimPoint = FVector::ZeroVector;

	FVector SpawnLocation = FVector::ZeroVector;
	float SpawnYaw = 0.f;
	FVector LastLocation = FVector::ZeroVector;
	float TravelSinceReset = 0.f;

	// foot IK smoothing state
	float FootOffsetSmoothed[2] = {0.f, 0.f};
	FVector FootNormalSmoothed[2] = { FVector::UpVector, FVector::UpVector };
	float PelvisOffsetSmoothed = 0.f;
	float FootIKAlphaSmoothed = 0.f;
	float LastCapsuleZ = 0.f;
	bool bHaveCapsuleZ = false;
	float NotGroundedTime = 0.f;

	// FX pool
	struct FFxItem
	{
		TWeakObjectPtr<UStaticMeshComponent> Comp;
		float Life = 0.f;
		float MaxLife = 0.f;
		FVector Start = FVector::ZeroVector;
		FVector End = FVector::ZeroVector;
		float Thickness = 1.f;
		float Radius = 0.f;
		FLinearColor Color = FLinearColor::White;
		bool bTracer = true;
		bool bFollowMuzzle = false;
	};
	// autopilot (used for the extra instances of the 1/10 Operatives toggle)
	FRandomStream ApRandom;
	bool bApInit = false;
	float ApTimer = 0.f;
	int32 ApMode = -1;
	FVector ApHome = FVector::ZeroVector;
	FVector ApTarget = FVector::ZeroVector;
	float ApSpeed = 0.f;
	bool bApChannel = false;
	float ApChannelTimer = 0.f;

	TArray<FFxItem> FxItems;
	TWeakObjectPtr<UStaticMeshComponent> BeamComp;
	TWeakObjectPtr<UStaticMeshComponent> OrbComp;
	TWeakObjectPtr<UStaticMeshComponent> RingComp;
	bool bBeamOn = false;
	bool bRingOn = false;

	TWeakObjectPtr<AActor> WorldBeacon;
	int32 ShotsFired = 0;
	int32 BladeHitsTotal = 0;
	TSet<TWeakObjectPtr<AActor>> BladeHitThisWindow;
	int32 LastMeleeWindowSerial = -1;
	FVector LastBladeBase = FVector::ZeroVector, LastBladeTip = FVector::ZeroVector;
	bool bHaveBlade = false;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> FxMaterials;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> FxBase;
};
