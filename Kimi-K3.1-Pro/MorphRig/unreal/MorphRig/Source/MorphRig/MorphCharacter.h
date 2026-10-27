#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MorphAnimInstance.h"
#include "MorphCharacter.generated.h"

class UAudioComponent;
class UCameraComponent;
class USoundWave;
class UStaticMesh;
class UStaticMeshComponent;
class UTextRenderComponent;

UENUM()
enum class EMorphCameraMode : uint8
{
    ThirdPerson,
    Front,
    Side,
    TopDown,
    Face
};

UENUM()
enum class EMorphControlState : uint8
{
    Locomotion,
    Action,
    Jump,
    Blink,
    Channel,
    Charge,
    Uplink,
    Stun,
    Sleep,
    Knockup,
    Prone,
    Dead,
    Respawn,
    Manual
};

UCLASS()
class MORPHRIG_API AMorphCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    AMorphCharacter();

    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
    virtual void Landed(const FHitResult& Hit) override;

    UMorphAnimInstance* GetMorphAnim() const;
    bool RequestClip(FName Id);
    void PlayDialogue();
    void ResetShowcase();
    void SetCameraMode(EMorphCameraMode Mode);
    void CycleCamera();
    void SetTeam(int32 TeamIndex);
    void SetLOD(int32 LODIndex);
    void ToggleSkeletonDebug();
    bool IsSkeletonDebug() const { return bSkeletonDebug; }
    void SetLocomotionDrive(float Speed, float DirectionDegrees);
    void StopLocomotionDrive();
    void RequestTurn(float Degrees);
    void RequestJump();
    void RequestDash(FName Direction = TEXT("f"));
    void RequestBlink();
    void RequestMelee(int32 Index);
    void RequestRanged(bool bBurst);
    void RequestReload();
    void RequestCast(FName CastId);
    void RequestDeploy();
    void StartChannel();
    void FinishChannel();
    void InterruptChannel();
    void StartCharge();
    void ReleaseCharge();
    void CancelCharge();
    void StartUplink();
    void FinishUplink();
    void CancelUplink();
    void ApplyHit(FName Direction);
    void StartStun();
    void EndStun();
    void StartSleep();
    void EndSleep();
    void Knockup();
    void Knockback();
    void Knockdown(bool bFront);
    void GetUp();
    void Die(bool bFront);
    void Respawn();
    void SetRooted(bool bValue);
    void SetSilenced(bool bValue);
    void SetDisarmed(bool bValue);
    void SetStasis(bool bValue);
    void SetWounded(bool bValue);
    void SetAutomationDriven(bool bValue) { bAutomationDriven = bValue; }
    void SetRemotePerformer(bool bValue) { bRemotePerformer = bValue; }
    bool IsAutomationDriven() const { return bAutomationDriven; }
    bool IsDirectClip() const { return bDirectClip; }

    EMorphCameraMode GetCameraMode() const { return CameraMode; }
    EMorphControlState GetControlState() const { return ControlState; }
    int32 GetTeam() const { return Team; }
    int32 GetLOD() const { return ForcedLOD; }
    float GetDriveSpeed() const { return DriveSpeed; }
    float GetDriveDirection() const { return DriveDirection; }
    float GetAimYaw() const { return AimYaw; }
    float GetAimPitch() const { return AimPitch; }
    void SetAim(float Yaw, float Pitch);
    void SetEyeLook(float LeftYaw, float LeftPitch, float RightYaw, float RightPitch);
    float GetEyeLeftYaw() const { return EyeLeftYaw; }
    float GetEyeLeftPitch() const { return EyeLeftPitch; }
    float GetEyeRightYaw() const { return EyeRightYaw; }
    float GetEyeRightPitch() const { return EyeRightPitch; }
    bool IsDead() const { return bDead; }
    bool IsRooted() const { return bRooted; }
    bool IsSilenced() const { return bSilenced; }
    bool IsDisarmed() const { return bDisarmed; }
    bool IsStasis() const { return bStasis; }
    bool IsWounded() const { return bWounded; }
    bool IsDialoguePlaying() const;
    FString GetPropState() const { return PropState; }
    FString GetCameraModeName() const;
    FString GetStateName() const;
    FString GetLastNativeEvent() const { return LastNativeEvent; }
    UCameraComponent* GetShowcaseCamera() const { return ShowcaseCamera; }
    bool IsDeployedBeaconVisible() const;
    FVector GetDeployedBeaconPosition() const;

protected:
    UPROPERTY(VisibleAnywhere) UCameraComponent* ShowcaseCamera;
    UPROPERTY(VisibleAnywhere) UAudioComponent* DialogueAudio;
    UPROPERTY(VisibleAnywhere) UTextRenderComponent* TeamBadge;
    UPROPERTY(VisibleAnywhere) UStaticMeshComponent* EffectMesh;
    UPROPERTY(VisibleAnywhere) UStaticMeshComponent* DeployedBeacon;

private:
    UFUNCTION() void HandleMorphEvent(const FMorphRuntimeEvent& Event);
    void SetControlState(EMorphControlState NewState, const FString& Reason);
    void UpdateMovement(float DeltaSeconds);
    void UpdateAutomaticAnimation(bool bDriveLocomotion);
    void UpdateGroundCompensation(float DeltaSeconds);
    void UpdateGroundIK();
    void UpdateCamera(float DeltaSeconds);
    void UpdateEffect(float DeltaSeconds);
    void CacheRestFootHeights();
    void RestoreProps();
    void TriggerEffect(FName EventName);
    bool CanFullBodyAction() const;
    bool CanUpperBodyAction() const;
    void MoveForward(float Value);
    void MoveRight(float Value);
    void LookUp(float Value);
    void LookYaw(float Value);
    void SprintPressed();
    void SprintReleased();
    void DashForward();
    void FireSingle();
    void FireBurst();
    void MeleePrimary();
    void TurnLeft90();
    void TurnRight90();
    void ToggleTeam();
    void ToggleGuide();

    UPROPERTY() USoundWave* DialogueWave = nullptr;
    UPROPERTY() UStaticMesh* DeployedBeaconAsset = nullptr;
    EMorphControlState ControlState = EMorphControlState::Locomotion;
    EMorphCameraMode CameraMode = EMorphCameraMode::ThirdPerson;
    FMorphAnimSnapshot LastSnapshot;
    FName LastDirectClip;
    FString PropState = TEXT("cell:seated beacon:stowed");
    FString LastNativeEvent;
    float DriveSpeed = 0.0f;
    float DriveDirection = 0.0f;
    float KeyboardForward = 0.0f;
    float KeyboardRight = 0.0f;
    float AimYaw = 0.0f;
    float AimPitch = 0.0f;
    float EyeLeftYaw = 0.0f;
    float EyeLeftPitch = 0.0f;
    float EyeRightYaw = 0.0f;
    float EyeRightPitch = 0.0f;
    float CameraOrbitYaw = 0.0f;
    float CameraOrbitPitch = 0.0f;
    float PreviousHorizontalSpeed = 0.0f;
    float FallImpactSpeed = 0.0f;
    float EffectRemaining = 0.0f;
    float RemoteClock = 0.0f;
    float MeshGroundOffset = 0.0f;
    float RestAnkleHeight[2] = { 0.0f, 0.0f };
    FVector InitialLocation = FVector::ZeroVector;
    FName LastGroundClip;
    FVector LastGroundLocation = FVector::ZeroVector;
    FQuat LastGroundRotation = FQuat::Identity;
    int32 Team = 0;
    int32 ForcedLOD = 0;
    bool bAnalogDrive = false;
    bool bSprinting = false;
    bool bWaitingTakeoff = false;
    bool bDirectClip = false;
    bool bDead = false;
    bool bRooted = false;
    bool bSilenced = false;
    bool bDisarmed = false;
    bool bStasis = false;
    bool bWounded = false;
    bool bAutomationDriven = false;
    bool bRemotePerformer = false;
    bool bRestHeightsCached = false;
    bool bSkeletonDebug = false;
};
