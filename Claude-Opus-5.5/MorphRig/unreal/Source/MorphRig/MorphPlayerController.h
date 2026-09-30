#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "MorphPlayerController.generated.h"

class AMorphOperative;
class AMorphShowcaseGameMode;

UENUM()
enum class EMorphCamera : uint8 { ThirdPerson, TopDown, Side, Front, Face, Free };

/**
 * Keyboard / mouse control of the showcase (polled every tick so it works with any input setup).
 * The key map is shown in-game (F1) and documented in README / docs.
 */
UCLASS()
class MORPHRIG_API AMorphPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AMorphPlayerController();
	virtual void BeginPlay() override;
	virtual void PlayerTick(float DeltaTime) override;

	AMorphOperative* Op() const;
	void SetCamMode(EMorphCamera M);
	EMorphCamera GetCameraMode() const { return CamMode; }
	FString CameraName() const;
	bool IsHelpVisible() const { return bHelp; }
	bool IsSkeletonOverlay() const { return bSkeleton; }
	bool IsAimOnTarget() const { return bAimAtTarget; }
	int32 GetSelectedTarget() const { return SelTarget; }
	void SetUIFocus(bool bUI);
	bool bScripted = false;          // deterministic sequence / capture drive the character
	bool bCapture = false;           // video capture: ignore all input (the window may grab the desktop keyboard)

private:
	void HandleKeys(float Dt);
	void UpdateCamera(float Dt);
	void DrawSkeleton() const;
	bool Pressed(const FKey& K) const { return WasInputKeyJustPressed(K); }
	bool Released(const FKey& K) const { return WasInputKeyJustReleased(K); }
	bool Down(const FKey& K) const { return IsInputKeyDown(K); }
	AMorphShowcaseGameMode* GM() const;

	EMorphCamera CamMode = EMorphCamera::ThirdPerson;
	float ArmScale = 1.f;
	float OrbitYaw = 0.f;
	bool bHelp = true;
	bool bSkeleton = false;
	bool bAimAtTarget = false;
	bool bAimLock = false;
	bool bWalk = false;
	int32 SelTarget = 0;
	float RMBDownTime = -1.f;
	bool bUIFocus = false;
};
