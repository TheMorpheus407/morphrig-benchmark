#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundWave.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigCharacter.generated.h"

UENUM(BlueprintType)
enum class EMorphRigPriority : uint8
{
	Locomotion = 0,
	JumpAir = 1,
	CombatAbility = 2,
	EvadeDashBlink = 3,
	CrowdControl = 4,
	Knockdown = 5,
	Terminal = 6
};

USTRUCT()
struct FMorphRigEventMarker
{
	GENERATED_BODY()

	UPROPERTY()
	FName EventName = NAME_None;

	UPROPERTY()
	float TimeSeconds = 0.0f;
};

USTRUCT()
struct FMorphRigClipEntry
{
	GENERATED_BODY()

	UPROPERTY()
	FName ClipId = NAME_None;

	UPROPERTY()
	FString Category;

	UPROPERTY()
	bool bLooping = false;

	UPROPERTY()
	bool bUpperBodyCapable = false;

	UPROPERTY()
	bool bAdditiveHit = false;

	UPROPERTY()
	EMorphRigPriority Priority = EMorphRigPriority::Locomotion;

	UPROPERTY()
	FName NextChainClip = NAME_None;

	UPROPERTY()
	TObjectPtr<UAnimSequence> Sequence = nullptr;

	UPROPERTY()
	TArray<FMorphRigEventMarker> Markers;
};

UCLASS()
class MORPHRIG_API AMorphRigCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AMorphRigCharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	// Action playback & state transitions
	bool RequestActionById(FName ClipId, bool bForceOverride = false);
	void InterruptCurrentAction();
	void TriggerMeleeCombo();
	void TriggerRangedSingle();
	void TriggerRangedBurst();
	void TriggerReload();
	void ToggleChannel();
	void StartOrReleaseCharge();
	void TriggerDeploy();
	void ToggleUplink();
	void TriggerDash(FName DashId = TEXT("dash_f"));
	void TriggerBlinkTeleport();
	void TriggerHitReaction(FName HitId = TEXT("hit_f"));
	void TriggerStun();
	void TriggerKnockdown(bool bFront = false);
	void TriggerSleep();
	void TriggerDeath(bool bFront = true);
	void TriggerRespawn();
	void TriggerSpokenDialogue();

	// Visual & runtime controls
	void SetTeamVariant(int32 NewTeamIndex); // 0 = TeamA (Cyan), 1 = TeamB (Amber)
	void ToggleTeamVariant();
	void SetForcedLODLevel(int32 NewLODIndex); // 0 = LOD0, 1 = LOD1, 2 = LOD2
	void CycleLODLevel();
	void CycleFacialExpression();
	void TriggerManualBlink();
	void SetPlaybackSpeed(float NewSpeed);

	// Accessors for HUD and Showcase Runner
	UMorphRigAnimInstance* GetMorphRigAnim() const { return MorphAnimInstance; }
	const TArray<FMorphRigClipEntry>& GetAllClips() const { return ClipRegistry; }
	FName GetCurrentActionId() const { return CurrentActionId; }
	EMorphRigPriority GetCurrentPriority() const { return CurrentPriority; }
	int32 GetTeamVariant() const { return TeamVariantIndex; }
	int32 GetCurrentLOD() const { return CurrentLODIndex; }
	float GetPlaybackSpeed() const { return PlaybackSpeed; }
	FName GetActiveExpressionName() const { return ActiveExpressionName; }
	const TArray<FString>& GetRecentEvents() const { return RecentEventLog; }

	// Aim target world location updated by GameMode / Player Input
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FVector AimTargetWorldLocation = FVector(280.0f, 0.0f, 145.0f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	bool bIsPrimaryShowcaseCharacter = true;

protected:
	void InitializeCatalogAndLoadAssets();
	void UpdateLocomotionAndState(float DeltaTime);
	void UpdateDashAndBlinkMotion(float DeltaTime);
	void UpdatePropAttachments(float PrevTime, float CurrTime);
	void EvaluateClipMarkers(float PrevTime, float CurrTime);
	void UpdateSlopeAndStepGroundIK(float DeltaTime);
	void UpdateAimAndLookAt(float DeltaTime);
	void LogAnimEvent(FName EventName, float ClipTime);

	UPROPERTY(VisibleAnywhere, Transient)
	TObjectPtr<UMorphRigAnimInstance> MorphAnimInstance = nullptr;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UAudioComponent> DialogueAudioComp = nullptr;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UStaticMeshComponent> PropCellComp = nullptr;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UStaticMeshComponent> PropBeaconComp = nullptr;

	UPROPERTY(Transient)
	TObjectPtr<USoundWave> DialogueSoundWave = nullptr;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> TeamAccentMID = nullptr;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexTeamA_D = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexTeamA_E = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexTeamB_D = nullptr;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> TexTeamB_E = nullptr;

	UPROPERTY()
	TArray<FMorphRigClipEntry> ClipRegistry;

	TMap<FName, int32> ClipIndexMap;

	FName CurrentActionId = TEXT("idle_combat");
	EMorphRigPriority CurrentPriority = EMorphRigPriority::Locomotion;
	float ActionElapsed = 0.0f;
	float LoopAutoAdvanceTimer = 0.0f;
	int32 MeleeComboStage = 0;
	bool bComboWindowOpen = false;
	bool bQueuedNextMelee = false;
	bool bWalkMode = false;

	// Dash & Blink state
	bool bIsDashing = false;
	FVector ActiveDashDirection = FVector::ForwardVector;
	float ActiveDashDuration = 0.40f;

	// Prop state
	bool bBeaconDetachedInWorld = false;
	FVector DetachedBeaconWorldLoc = FVector::ZeroVector;

	// Facial & runtime settings
	int32 TeamVariantIndex = 0;
	int32 CurrentLODIndex = 0;
	int32 ExpressionPresetIndex = 0;
	FName ActiveExpressionName = TEXT("Neutral");
	float PlaybackSpeed = 1.0f;
	float ManualBlinkTimer = 0.0f;
	float DialogueTimer = 0.0f;
	bool bPlayingDialogue = false;

	TArray<FString> RecentEventLog;
};
