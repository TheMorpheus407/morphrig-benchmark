// MORPHRIG: input, cameras and every showcase command. All commands are public so the Slate panel, the deterministic sequence and the
// keyboard bindings call the same functions.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "OperativeTypes.h"
#include "OperativeCharacter.h"
#include "ShowcasePlayerController.generated.h"

class ACameraActor;
class AShowcaseRoom;
class AShowcaseDirector;
class SShowcasePanel;
class UOperativeActionComponent;

UENUM(BlueprintType)
enum class EShowcaseView : uint8
{
	ThirdPerson,   // close inspection over the shoulder
	Front,         // full body front
	Side,          // full body side
	TopDown,       // 55 degrees, character about 120 px tall
	Face,          // face close up
	Hands,         // prop contact close up (cell, beacon, emitter)
	Orbit          // full body orbit (turntable capture), not part of the view cycle
};

struct FShowcaseBinding
{
	FString KeyText;
	FString Description;
	FString Category;
};

UCLASS()
class MORPHRIG_API AShowcasePlayerController : public APlayerController
{
	GENERATED_BODY()
public:
	AShowcasePlayerController();
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	AOperativeCharacter* GetOperative() const;
	UOperativeActionComponent* GetActions() const;
	AShowcaseRoom* GetRoom() const;
	AShowcaseDirector* GetDirector() const;
	void SetDirector(AShowcaseDirector* D);

	// ------------------------------------------------------------------ commands: mobility and combat
	void CmdJump();
	void CmdDash();
	void CmdBlink();
	void CmdFire();
	void CmdBurst();
	void CmdMelee();
	void CmdReload();
	void CmdCastDirectional();
	void CmdCastGround();
	void CmdCastSelf();
	void CmdChannelPressed();
	void CmdChannelReleased();
	void CmdChargePressed();
	void CmdChargeReleased();
	void CmdChargeCancel();
	void CmdDeploy();
	void CmdUplink();
	void CmdInterrupt();
	void CmdGreet();
	void CmdVictory();
	void CmdDefeat();
	void CmdDialogue();
	// ------------------------------------------------------------------ hits and disables
	void CmdHit(int32 Direction);     // 0 front, 1 back, 2 left, 3 right (side the hit comes from)
	void CmdStun();
	void CmdSleepToggle();
	void CmdKnockback();
	void CmdKnockup();
	void CmdKnockdown(bool bHitFromFront);
	void CmdKill();
	void CmdRespawn();
	void CmdReset();
	void CmdToggleRoot();
	void CmdToggleSilence();
	void CmdToggleDisarm();
	void CmdToggleStasis();
	// ------------------------------------------------------------------ locomotion and aim
	void SetGait(EOperativeGait G) { Gait = G; }
	EOperativeGait GetGait() const { return Gait; }
	void SetManualLocomotion(bool bOn, float AngleLeftDeg, float SpeedCmS);
	bool IsManualLocomotion() const { return bManualLoco; }
	float GetManualAngle() const { return ManualAngle; }
	float GetManualSpeed() const { return ManualSpeed; }
	void SetManualAim(bool bOn, float YawLeftDeg, float PitchUpDeg);
	bool IsManualAim() const { return bManualAim; }
	void CycleFacingMode();
	void SetFacingMode(EOperativeFacingMode M);
	void SetActionRate(float Rate);
	void AdjustActionRate(float Delta);
	void ToggleAimHold() { bAimToggle = !bAimToggle; }
	void SetAimToggle(bool b) { bAimToggle = b; }
	bool GetAimToggle() const { return bAimToggle; }
	void SetLookAtCamera(bool b);
	bool GetLookAtCamera() const { return bLookAtCamera; }
	// ------------------------------------------------------------------ view and render
	void SetView(EShowcaseView V);
	void CycleView();
	EShowcaseView GetView() const { return View; }
	void CycleRenderMode();
	void SetRenderMode(int32 M);
	void CycleLOD();
	void SetLOD(int32 Lod);
	void ToggleTeam();
	void SetTeam(EOperativeTeam T);
	void ToggleOverlay() { OverlayMode = (OverlayMode + 1) % 4; }
	void SetOverlayMode(int32 M) { OverlayMode = FMath::Clamp(M, 0, 3); }
	int32 GetOverlayMode() const { return OverlayMode; }
	void ToggleHelp() { bHelp = !bHelp; }
	bool IsHelpVisible() const { return bHelp; }
	void ToggleOutline();
	void SetOutline(bool bOn) { if (bOutline != bOn) ToggleOutline(); }
	void SetCameraAvoid(bool bOn) { bCameraAvoid = bOn; }
	void ToggleStudio();
	bool IsStudio() const;
	void TogglePanel();
	void ToggleInstances();
	void SetInstances(int32 Count);
	void ToggleTargetsPatrol();
	void SelectNextTarget();
	void MoveSelectedTargetToCursor();
	void ToggleMotionViewerStation();
	void SetOrbit(float Yaw, float Pitch, float Distance);
	void SetCameraLocked(bool b) { bCameraSnap = b; }
	void ResetCameraSmoothing() { bCameraSnap = true; }
	void SetCursorAimEnabled(bool b) { bCursorAim = b; }
	void StartSequence();
	// ------------------------------------------------------------------ animation browser
	bool BrowserPlay(FName ClipId);
	void BrowserStop();
	void BrowserSetRate(float R);
	float GetBrowserRate() const { return BrowserRate; }
	void BrowserSetLoop(bool b) { bBrowserLoop = b; }
	bool GetBrowserLoop() const { return bBrowserLoop; }
	FName GetBrowserClip() const { return BrowserClip; }
	// ------------------------------------------------------------------ face
	void FaceSetPreset(FName Preset);
	void FaceClear();

	// ------------------------------------------------------------------ queries for HUD and panel
	int32 GetInstanceCount() const { return InstanceCount; }
	FVector GetAimPoint() const { return AimPoint; }
	FString GetViewName() const;
	FString GetRenderModeName() const;
	FString GetFacingModeName() const;
	const TArray<FShowcaseBinding>& GetBindings() const { return Bindings; }
	float GetCharacterPixelHeight() const { return CharacterPixelHeight; }
	bool IsPanelVisible() const { return bPanelVisible; }
	FVector2D GetHeadScreen() const { return HeadScreen; }
	FVector2D GetFeetScreen() const { return FeetScreen; }

	/** Inputs used by the sequence to drive the character without a keyboard. */
	void SequenceMove(const FVector& WorldDir, float Speed);
	void SequenceAim(const FVector& WorldPoint);
	bool bSequenceControl = false;

private:
	void BuildBindings();
	void Bind(const FKey& Key, EInputEvent Ev, TFunction<void()> Fn, bool bShift = false, bool bCtrl = false, bool bAlt = false);
	void AddDoc(const TCHAR* Category, const TCHAR* Keys, const TCHAR* Desc);
	void UpdateMovement(float Dt);
	void UpdateAim(float Dt);
	void UpdateCamera(float Dt);
	void UpdateOverlays();
	void EnsureCamera();
	float CurrentGaitSpeed() const;
	FVector CameraForwardFlat() const;
	FVector HitDirectionWorld(int32 Direction) const;
	void SpawnInstances(int32 Count);

	TWeakObjectPtr<AShowcaseDirector> Director;
	UPROPERTY() TObjectPtr<ACameraActor> CameraActor;
	UPROPERTY() TArray<TObjectPtr<AOperativeCharacter>> ExtraOperatives;
	TSharedPtr<SShowcasePanel> Panel;
	TSharedPtr<class SWidget> PanelHolder;
	TArray<FShowcaseBinding> Bindings;

	EOperativeGait Gait = EOperativeGait::Run;
	bool bManualLoco = false;
	float ManualAngle = 0.f, ManualSpeed = 0.f;
	bool bManualAim = false;
	float ManualAimYaw = 0.f, ManualAimPitch = 0.f;
	bool bAimToggle = false;
	bool bLookAtCamera = false;
	bool bCursorAim = true;
	bool bChannelHeld = false;
	bool bChargeHeld = false;

	EShowcaseView View = EShowcaseView::ThirdPerson;
	float OrbitYaw = 200.f;       // camera yaw for orbiting views (world)
	float OrbitPitch = -10.f;
	float OrbitDistance = 390.f;
	bool bCameraSnap = false;
	int32 OverlayMode = 0;
	bool bHelp = false;
	bool bPanelVisible = true;
	int32 InstanceCount = 1;
	FVector AimPoint = FVector::ZeroVector;
	FVector SequenceMoveDir = FVector::ZeroVector;
	float SequenceMoveSpeed = 0.f;
	FVector SequenceAimPoint = FVector::ZeroVector;
	bool bSleeping = false;
	bool bOutline = true;
	bool bCameraAvoid = true;         // camera collision and free-direction search (UpdateCamera)
	float CamAvoidYaw = 0.f, CamAvoidTarget = 0.f, CamClearTime = 0.f;
	float FaceCameraYaw = -9.f;     // degrees from the character's facing, negative = the character's right side

	FName BrowserClip;
	float BrowserRate = 1.f;
	bool bBrowserLoop = false;

	float CharacterPixelHeight = 0.f;
	FVector2D HeadScreen = FVector2D::ZeroVector;
	FVector2D FeetScreen = FVector2D::ZeroVector;
	bool bMotionViewerStation = false;
	FVector StationReturnLocation = FVector::ZeroVector;
	float MouseX = 0.f, MouseY = 0.f;
	bool bOrbitDrag = false;
};
