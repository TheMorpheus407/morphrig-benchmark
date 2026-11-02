// MorphRig - the playable Operative.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputCoreTypes.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigCharacter.generated.h"

class UCameraComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UAnimSequenceBase;
class ULineBatchComponent;

/** Camera framing modes offered by the showcase. */
UENUM(BlueprintType)
enum class EMorphRigCameraMode : uint8
{
	/** Close third person, over the shoulder. */
	Close,
	/** Full body, side on. */
	FullBodySide,
	/** Full body, front on. */
	FullBodyFront,
	/** Top down. */
	TopDown,
	/** Face only. */
	Face
};

/**
 * How the Operative is shaded in the showcase.
 *
 * The showcase has to show the mesh, the normals and the authored textures,
 * so the eight material slots are swapped for two helper materials while the
 * view is not "textured".
 */
UENUM(BlueprintType)
enum class EMorphRigMaterialView : uint8
{
	/** The authored textured materials. */
	Textured,
	/** The world space normal of the surface. */
	Normal,
	/** A flat grey, no textures, no normals. */
	Clay
};

/**
 * The Operative character.
 *
 * Owns the camera rig, the input handling, the state machine that drives the
 * animation controller and the deterministic showcase sequence.
 */
UCLASS()
class MORPHRIG_API AMorphRigCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AMorphRigCharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PossessedBy(AController* NewController) override;

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetCameraMode(EMorphRigCameraMode InMode);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	EMorphRigCameraMode GetCameraMode() const { return CameraMode; }

	/** Team accent, 0 = amber, 1 = cyan. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetTeam(int32 InTeam);

	/** Forced LOD, 0..2. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetLOD(int32 InLOD);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetShowSkeleton(bool bInShow);

	/** Switch the shading of the Operative: textured, normal or clay. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetMaterialView(EMorphRigMaterialView InView);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	EMorphRigMaterialView GetMaterialView() const { return MaterialView; }

	/** The name of the current shading, for the HUD. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	FString GetMaterialViewName() const;

	/** Cycle textured, normal and clay. */
	UFUNCTION()
	void ToggleMaterialView();

	/** Play one of the 96 required clips by name. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	bool PlayClip(const FString& ClipName, float InPlayRate = 1.0f);

	/** Play a one shot action (melee, cast, dash ...). */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	bool TriggerAction(const FString& ClipName);

	/** Reset the character back to the neutral stance. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ResetCharacter();

	/** Teleport (blink) to a destination, playing the blink clips. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void BlinkTo(const FVector& Destination);

	/** Apply a hit reaction from a world direction. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyHit(FVector FromWorldDirection);

	/** Start the deterministic showcase sequence. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void StartShowcaseSequence();

	/** Stop the deterministic showcase sequence. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void StopShowcaseSequence();

	/** Play the spoken performance: the dialogue clip plus its audio. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void PlayPerformance();

	/** Open or close the searchable animation browser. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ToggleAnimationBrowser();

	/** Toggle between one and ten Operatives in the room. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ToggleInstanceCount();

	/** How many Operatives are in the room, including the player. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	int32 GetInstanceCount() const { return 1 + ExtraInstances.Num(); }

	/** Read the command line options of the client. */
	void ApplyCommandLineOptions();

	/** Draw the skeleton of the character as coloured lines. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void UpdateSkeletonOverlay();

	/** Keep the feet on the floor of the room. */
	void UpdateGroundAdaptation();

	/** Append text to the animation browser filter. */
	void AppendToBrowserFilter(const FString& Characters);

	/** Remove the last character from the animation browser filter. */
	UFUNCTION()
	void BackspaceBrowserFilter();

	/** Key handler for the animation browser filter. */
	UFUNCTION()
	void AppendFilterKey(FKey Key);

	/** Move the browser selection up or down. */
	UFUNCTION()
	void MoveBrowserSelection(int32 Delta);

	/** Play the clip that is selected in the browser. */
	UFUNCTION()
	void PlaySelectedClip();

	/** Step the playback rate of the base layer, 0.5x to 1.5x. */
	UFUNCTION()
	void StepPlayRate(float Delta);

	/** The playback rate of the base layer. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetPlayRate() const { return PlayRate; }

	/** The index of the selected clip in the browser. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	int32 GetBrowserSelection() const { return BrowserSelection; }

	UFUNCTION()
	void MoveBrowserSelectionUp();

	UFUNCTION()
	void MoveBrowserSelectionDown();

	UFUNCTION()
	void SlowerPlayback();

	UFUNCTION()
	void FasterPlayback();

	/** The current animation browser filter text. */
	const FString& GetBrowserFilter() const { return BrowserFilter; }

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	bool IsShowcaseRunning() const { return bShowcaseRunning; }

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	const TArray<FString>& GetTrace() const { return Trace; }

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	UMorphRigAnimInstance* GetMorphAnimInstance() const;

	/** The active team accent index, 0 = amber, 1 = cyan. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	int32 GetTeamIndex() const { return TeamIndex; }

	/** The forced LOD index, 0..2. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	int32 GetLODIndex() const { return LODIndex; }

	/** The active camera framing mode. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	EMorphRigCameraMode GetCameraModeIndex() const { return CameraMode; }

	/** Search the animation inventory, returns the matching clip names. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static TArray<FString> SearchClips(const FString& Filter);

	/** Every imported clip name. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static TArray<FString> GetAllClipNames();

	/** Look a clip up in the loaded library. */
	UAnimSequenceBase* FindClip(const FString& ClipName) const;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	EMorphRigCameraMode CameraMode = EMorphRigCameraMode::Close;

	/** Seconds between two camera modes, 0 = the camera stays where it is. */
	float CameraCycleSeconds = 0.0f;

	/** Time since the last camera change while the camera cycles. */
	float CameraCycleTimer = 0.0f;

	/** Directory for the screenshots, empty = no screenshots are taken. */
	FString ShotDirectory;

	/** The shading asked for on the command line, applied once the mesh is up. */
	FString PendingMaterialView;

	/** Seconds until the first screenshot is taken. */
	float ShotDelay = 0.0f;

	/** Time since the start of the game. */
	float GameTime = 0.0f;

	/** True once the first screenshot has been taken. */
	bool bShotTaken = false;

	/** Where the dash started, so the distance can be measured. */
	FVector DashStartLocation = FVector::ZeroVector;

	void TakeScreenshot(const FString& Suffix);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	float WalkSpeed = 420.0f;

	/** Speed limit while a dash clip drives the capsule, in cm/s. */
	float DashSpeed = 2400.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	float RunSpeed = 780.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	float TurnRate = 220.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	bool bShowSkeletonOverlay = false;

	/** The current shading of the Operative. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	EMorphRigMaterialView MaterialView = EMorphRigMaterialView::Textured;

	/** The authored materials of the eight slots, kept to restore the view. */
	UPROPERTY()
	TArray<TObjectPtr<UMaterialInterface>> AuthoredMaterials;

	/** The world space normal helper material. */
	UPROPERTY()
	TObjectPtr<UMaterialInterface> NormalViewMaterial;

	/** The flat grey helper material. */
	UPROPERTY()
	TObjectPtr<UMaterialInterface> ClayViewMaterial;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	int32 TeamIndex = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	int32 LODIndex = 0;

	/** True for the copies spawned by ToggleInstanceCount. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "MorphRig")
	bool bIsShowcaseInstance = false;

	/** All clips indexed by name, loaded from the content folder. */
	TMap<FString, TObjectPtr<UAnimSequenceBase>> ClipLibrary;

	UPROPERTY()
	UMaterialInstanceDynamic* AccentMID = nullptr;

	UFUNCTION()
	void MoveForward(float Value);

	UFUNCTION()
	void MoveRight(float Value);

	UFUNCTION()
	void Turn(float Value);

	UFUNCTION()
	void LookUp(float Value);

	UFUNCTION()
	void JumpAction();

	UFUNCTION()
	void ToggleAim();

	UFUNCTION()
	void CycleCamera();

	UFUNCTION()
	void Fire();
	UFUNCTION()
	void Secondary();
	UFUNCTION()
	void Ability();
	UFUNCTION()
	void Dodge();
	UFUNCTION()
	void Interact();
	UFUNCTION()
	void ToggleTeam();
	UFUNCTION()
	void ToggleLOD();
	UFUNCTION()
	void ToggleSkeleton();
	UFUNCTION()
	void ResetChar();

	UFUNCTION()
	void PlaySpeech();

	UFUNCTION()
	void ToggleBrowser();

	UFUNCTION()
	void RunShowcase();

	UFUNCTION()
	void ToggleInstances();

	/** Load the 96 clips from the content folder. */
	void BuildClipLibrary();

	/** Advance the deterministic showcase sequence. */
	void TickShowcase(float DeltaSeconds);

	/** Update the camera for the current framing mode. */
	void UpdateCamera();

	/** Pick the locomotion clip that matches the current direction. */
	FString PickLocomotionClip() const;

	/** Set the high level state and the base clip together. */
	void SetState(EMorphRigState NewState, const FString& ClipName, bool bLoop = false);

	FString CurrentStateName() const;

private:
	UMorphRigAnimInstance* AnimInstance = nullptr;
	bool bAiming = false;
	bool bShowcaseRunning = false;
	float ShowcaseTimer = 0.0f;
	int32 ShowcaseStep = 0;
	TArray<FString> Trace;
	FVector PendingBlinkTarget = FVector::ZeroVector;
	bool bPendingBlink = false;
	float ActionWeight = 0.0f;
	float AimWeight = 0.0f;
	FString ActionClipName;
	float ActionTimer = 0.0f;
	float ActionDuration = 0.0f;
	FString ActiveActionClip;
	FString BrowserFilter;
	bool bBrowserOpen = false;
	int32 BrowserSelection = 0;
	float PlayRate = 1.0f;

	/** The smoothed offset that keeps the feet on the floor of the room. */
	float GroundOffset = 0.0f;

	/** The extra Operatives spawned by ToggleInstanceCount. */
	UPROPERTY()
	TArray<TObjectPtr<AMorphRigCharacter>> ExtraInstances;

	/** Draws the skeleton overlay when the option is enabled. */
	UPROPERTY()
	TObjectPtr<ULineBatchComponent> SkeletonLines;
};
