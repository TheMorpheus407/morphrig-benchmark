#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MorphRigTypes.h"
#include "MorphRigCharacter.generated.h"

class UMorphRigAnimInstance;
class UAudioComponent;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;
class UTexture2D;

UCLASS()
class MORPHRIG_API AMorphRigCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AMorphRigCharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	TObjectPtr<UAudioComponent> DialogueAudioComp;

	// Secondary non-color team icon mesh (Diamond for Team A, Double-Chevron for Team B)
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig|Team")
	TObjectPtr<UStaticMeshComponent> TeamIconMeshA;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig|Team")
	TObjectPtr<UStaticMeshComponent> TeamIconMeshB1;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig|Team")
	TObjectPtr<UStaticMeshComponent> TeamIconMeshB2;

	// Visual muzzle/beam/beacon presentation helpers
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig|VFX")
	TObjectPtr<UStaticMeshComponent> DeployedBeaconVisual;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MID_CyberArmor;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MID_PropsTech;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> MID_TeamBadge;

	// Cached Team A / B textures for instant material variant switching
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexArmorA_Base;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexArmorA_Emis;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexArmorB_Base;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexArmorB_Emis;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexPropsA_Base;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexPropsA_Emis;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexPropsB_Base;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexPropsB_Emis;

	// Gameplay & Showcase Controls
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Control")
	FVector2D DesiredMoveInput = FVector2D::ZeroVector; // X = Forward [-1..1], Y = Right [-1..1]

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Control")
	int32 SpeedTier = 1; // 0 = Walk (150 cm/s), 1 = Run (400 cm/s), 2 = Sprint (650 cm/s)

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Control")
	float DesiredFacingYaw = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Control")
	FVector WorldAimTarget = FVector(320.0f, 0.0f, 145.0f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Visual")
	int32 TeamIndex = 0; // 0 = Team A (Cyan + Diamond), 1 = Team B (Crimson-Amber + Double-Chevron)

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Visual")
	bool bShowSecondaryTeamCue = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Visual")
	int32 ForcedLODSelection = -1; // -1 = Auto, 0 = LOD0, 1 = LOD1, 2 = LOD2

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Visual")
	bool bShowSkeletonOverlay = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Visual")
	bool bWireframeMaterialMode = false;

	// Crowd instance support (for 1 vs 10 simultaneous Operatives benchmark/showcase)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Crowd")
	bool bIsCrowdInstance = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig|Crowd")
	int32 CrowdRoleIndex = 0;

	FVector SpawnOrigin = FVector::ZeroVector;
	float PrevDashTime = 0.0f;
	float KnockbackRemainingSpeed = 0.0f;
	float MuzzleFlashTimer = 0.0f;
	FVector LastMuzzleOrigin = FVector::ZeroVector;
	float PrevIdleSpeed = 0.0f;
	float AccumulatedTurnDelta = 0.0f;
	FVector PrevTravelDir = FVector::ForwardVector;

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	UMorphRigAnimInstance* GetMorphRigAnim() const;

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetTeamVariant(int32 NewTeamIndex, bool bEnableSecondaryCue);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetForcedLODMode(int32 LODMode);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void TriggerDialoguePerformance();

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ResetOperativeFull(const FVector& ResetWorldLocation, float ResetYaw = 0.0f);

	int32 GetCurrentDisplayedLOD() const;

private:
	UFUNCTION()
	void HandleAnimMarkerFired(const FMorphRigEventRecord& EventRec);

	void AlignMeshForwardToActorX();
	void InitDynamicMaterials();
	void DrawSkeletonAndSocketsDebug() const;
	void TickCrowdBehavior(float DeltaSeconds);
};
