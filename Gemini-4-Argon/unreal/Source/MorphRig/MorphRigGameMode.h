#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "MorphRigCharacter.h"
#include "MorphRigGameMode.generated.h"

UCLASS()
class MORPHRIG_API AMorphRigHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;
};

UCLASS()
class MORPHRIG_API AMorphRigPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AMorphRigPlayerController();

	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;

	AMorphRigCharacter* GetPrimaryOperative() const;

	// Browser & Camera state
	int32 SelectedClipBrowserIndex = 0;
	int32 CameraPresetIndex = 0; // 0=Orbit, 1=TopDown52Deg, 2=FaceCloseUp, 3=GroundIKSide
	float OrbitYaw = 155.0f;
	float OrbitPitch = -12.0f;
	float OrbitDistance = 285.0f;

	// Crowd benchmark state
	bool bCrowd10Active = false;
	TArray<TObjectPtr<AMorphRigCharacter>> CrowdCharacters;

	// Showcase Arena Actors
	UPROPERTY(Transient)
	TObjectPtr<AActor> AimTargetVisualActor = nullptr;
	FVector SlopeTestLocation = FVector(220.0f, -240.0f, 125.0f);
	FVector StepTestLocation = FVector(220.0f, 240.0f, 110.0f);
	FVector FlatCenterLocation = FVector(0.0f, 0.0f, 92.0f);

	// Deterministic Showcase Sequence Runner
	bool bRunningShowcaseSequence = false;
	bool bAutoQuitAfterShowcase = false;
	float ShowcaseTimer = 0.0f;
	int32 ShowcaseStage = -1;
	TArray<float> FpsSamples1Instance;
	TArray<float> FpsSamples10Instances;
	TArray<FString> ShowcaseTraceLines;

	void ToggleCrowd10Instances();
	void StartShowcaseSequence();
	void AdvanceShowcaseSequence(float DeltaTime);
	void WriteShowcaseTraceReport();

protected:
	void OnMoveForward(float Val);
	void OnMoveRight(float Val);
	void OnTurn(float Val);
	void OnLookUp(float Val);
	void OnAimTargetX(float Val);
	void OnAimTargetZ(float Val);

	void OnJumpPressed();
	void OnDashPressed();
	void OnBlinkPressed();
	void OnMeleePressed();
	void OnRangedFirePressed();
	void OnRangedBurstPressed();
	void OnReloadPressed();
	void OnChannelPressed();
	void OnChargePressed();
	void OnDeployPressed();
	void OnUplinkPressed();
	void OnInterruptPressed();
	void OnDialoguePressed();
	void OnExpressionPressed();
	void OnManualBlinkPressed();
	void OnToggleTeamPressed();
	void OnCycleLODPressed();
	void OnToggleCrowdPressed();
	void OnCycleCameraPressed();
	void OnPrevAnimPressed();
	void OnNextAnimPressed();
	void OnPlaySelectedAnimPressed();
	void OnSpeedDownPressed();
	void OnSpeedUpPressed();
	void OnHitPressed();
	void OnStunPressed();
	void OnKnockdownPressed();
	void OnSleepPressed();
	void OnDeathPressed();
	void OnRespawnPressed();
	void OnTeleportSlopePressed();
	void OnTeleportStepsPressed();
	void OnTeleportFlatPressed();
};

UCLASS()
class MORPHRIG_API AMorphRigGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMorphRigGameMode();

	virtual void StartPlay() override;

protected:
	void SpawnShowcaseArenaEnvironment();
};
