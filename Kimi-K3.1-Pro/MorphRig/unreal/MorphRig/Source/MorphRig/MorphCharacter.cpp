#include "MorphCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundWave.h"
#include "UObject/ConstructorHelpers.h"
#include "MorphGameMode.h"
#include "MorphRig.h"

AMorphCharacter::AMorphCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(38.0f, 90.0f);
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    GetMesh()->SetRelativeLocation(FVector(0.0, 0.0, -90.0));
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
    GetMesh()->SetRelativeScale3D(FVector::OneVector);
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    bUseControllerRotationPitch = false;
    bUseControllerRotationYaw = false;
    bUseControllerRotationRoll = false;

    GetCharacterMovement()->bOrientRotationToMovement = false;
    GetCharacterMovement()->bUseControllerDesiredRotation = false;
    GetCharacterMovement()->MaxWalkSpeed = 400.0f;
    GetCharacterMovement()->MaxWalkSpeedCrouched = 180.0f;
    GetCharacterMovement()->MaxStepHeight = 20.0f;
    GetCharacterMovement()->SetWalkableFloorAngle(20.5f);
    GetCharacterMovement()->JumpZVelocity = 500.0f;
    GetCharacterMovement()->AirControl = .65f;
    GetCharacterMovement()->BrakingDecelerationWalking = 1450.0f;
    GetCharacterMovement()->GroundFriction = 8.0f;

    bFindCameraComponentWhenViewTarget = true;
    ShowcaseCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ShowcaseCamera"));
    ShowcaseCamera->SetupAttachment(RootComponent);
    ShowcaseCamera->bUsePawnControlRotation = false;
    ShowcaseCamera->SetFieldOfView(60.0f);
    ShowcaseCamera->SetAspectRatioAxisConstraint(AspectRatio_MaintainYFOV);
    ShowcaseCamera->bOverrideAspectRatioAxisConstraint = true;
    ShowcaseCamera->PostProcessSettings.bOverride_MotionBlurAmount = true;
    ShowcaseCamera->PostProcessSettings.MotionBlurAmount = 0.0f;
    ShowcaseCamera->SetActive(true);

    DialogueAudio = CreateDefaultSubobject<UAudioComponent>(TEXT("DialogueAudio"));
    DialogueAudio->SetupAttachment(RootComponent);
    DialogueAudio->bAutoActivate = false;
    DialogueAudio->bAllowSpatialization = false;

    TeamBadge = CreateDefaultSubobject<UTextRenderComponent>(TEXT("TeamBadge"));
    TeamBadge->SetupAttachment(RootComponent);
    TeamBadge->SetRelativeLocation(FVector(0.0, 0.0, 108.0));
    TeamBadge->SetHorizontalAlignment(EHTA_Center);
    TeamBadge->SetVerticalAlignment(EVRTA_TextCenter);
    TeamBadge->SetWorldSize(17.0f);
    TeamBadge->SetText(FText::FromString(TEXT("I")));

    EffectMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("EventEffect"));
    EffectMesh->SetupAttachment(GetMesh());
    static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (SphereMesh.Succeeded())
    {
        EffectMesh->SetStaticMesh(SphereMesh.Object);
    }
    EffectMesh->SetRelativeScale3D(FVector(.065f));
    EffectMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    EffectMesh->SetVisibility(false);

    static ConstructorHelpers::FObjectFinder<UStaticMesh> BeaconAsset(TEXT("/Game/Operative/ST_Beacon.ST_Beacon"));
    DeployedBeaconAsset = BeaconAsset.Object;
    DeployedBeacon = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DeployedBeacon"));
    DeployedBeacon->SetupAttachment(RootComponent);
    DeployedBeacon->SetAbsolute(true, true, true);
    DeployedBeacon->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    DeployedBeacon->SetVisibility(false);
}

void AMorphCharacter::BeginPlay()
{
    Super::BeginPlay();
    InitialLocation = GetActorLocation();
    if (USkeletalMesh* SkeletalMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Operative/SK_Operative.SK_Operative")))
    {
        GetMesh()->SetSkeletalMeshAsset(SkeletalMesh);
    }
    else
    {
        UE_LOG(LogMorphRig, Error, TEXT("MR_ASSET missing mesh=/Game/Operative/SK_Operative"));
    }
    GetMesh()->SetAnimInstanceClass(UMorphAnimInstance::StaticClass());
    GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    if (UMorphAnimInstance* Anim = GetMorphAnim())
    {
        Anim->LoadNativeAssets();
        Anim->OnMorphEvent.AddDynamic(this, &AMorphCharacter::HandleMorphEvent);
        Anim->SetAim(0.0f, 0.0f, false);
    }
    DialogueWave = LoadObject<USoundWave>(nullptr, TEXT("/Game/Operative/Audio/Dialogue.Dialogue"));
    if (DialogueWave)
    {
        DialogueAudio->SetSound(DialogueWave);
    }
    else
    {
        UE_LOG(LogMorphRig, Warning, TEXT("MR_ASSET missing audio=/Game/Operative/Audio/Dialogue"));
    }

    for (const FName Socket : { FName(TEXT("emitter_muzzle")), FName(TEXT("Muzzle")), FName(TEXT("muzzle")), FName(TEXT("hand_R")) })
    {
        if (GetMesh()->DoesSocketExist(Socket) || GetMesh()->GetBoneIndex(Socket) != INDEX_NONE)
        {
            EffectMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, Socket);
            EffectMesh->SetRelativeScale3D(FVector(.065f));
            break;
        }
    }
    UMaterial* ShapeMaterial = LoadObject<UMaterial>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (ShapeMaterial)
    {
        UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(ShapeMaterial, this);
        Material->SetVectorParameterValue(TEXT("Color"), FLinearColor(.05f, .9f, 1.0f, 1.0f));
        EffectMesh->SetMaterial(0, Material);
    }
    DeployedBeacon->SetStaticMesh(DeployedBeaconAsset);
    CacheRestFootHeights();
    SetTeam(Team);
    SetLOD(ForcedLOD);
    SetControlState(EMorphControlState::Locomotion, TEXT("begin_play"));
}

UMorphAnimInstance* AMorphCharacter::GetMorphAnim() const
{
    return Cast<UMorphAnimInstance>(GetMesh()->GetAnimInstance());
}

bool AMorphCharacter::IsDeployedBeaconVisible() const
{
    return DeployedBeacon && DeployedBeacon->GetStaticMesh() && DeployedBeacon->IsVisible();
}

FVector AMorphCharacter::GetDeployedBeaconPosition() const
{
    return DeployedBeacon ? DeployedBeacon->GetComponentLocation() : FVector::ZeroVector;
}

void AMorphCharacter::Tick(const float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (bRemotePerformer)
    {
        RemoteClock += DeltaSeconds;
        if (RemoteClock > 1.0f && RemoteClock - DeltaSeconds <= 1.0f)
        {
            if (UMorphAnimInstance* Anim = GetMorphAnim())
            {
                Anim->RequestClip(Team == 0 ? TEXT("idle_combat") : TEXT("idle_relaxed"), .25f);
                Anim->SetAim(Team == 0 ? -15.0f : 15.0f, 0.0f, true);
            }
        }
    }
    else if (!bAutomationDriven)
    {
        UpdateMovement(DeltaSeconds);
    }
    UpdateAutomaticAnimation(!bAutomationDriven && !bRemotePerformer);
    if (GetCharacterMovement()->IsFalling())
    {
        FallImpactSpeed = GetCharacterMovement()->Velocity.Z;
    }
    UpdateGroundCompensation(DeltaSeconds);
    UpdateGroundIK();
    UpdateCamera(DeltaSeconds);
    UpdateEffect(DeltaSeconds);
    if (UMorphAnimInstance* Anim = GetMorphAnim())
    {
        LastSnapshot = Anim->GetSnapshot();
    }
}

bool AMorphCharacter::CanFullBodyAction() const
{
    return !bDead && !bStasis && ControlState != EMorphControlState::Dead && ControlState != EMorphControlState::Stun &&
        ControlState != EMorphControlState::Sleep && ControlState != EMorphControlState::Knockup &&
        ControlState != EMorphControlState::Prone && ControlState != EMorphControlState::Respawn;
}

bool AMorphCharacter::CanUpperBodyAction() const
{
    return !bDead && !bStasis && ControlState == EMorphControlState::Locomotion;
}

void AMorphCharacter::SetControlState(const EMorphControlState NewState, const FString& Reason)
{
    if (NewState != EMorphControlState::Manual)
    {
        bDirectClip = false;
    }
    if (ControlState == NewState)
    {
        return;
    }
    const FString OldState = GetStateName();
    ControlState = NewState;
    UE_LOG(LogMorphRig, Log, TEXT("MR_STATE actor=%s old=%s new=%s clip=%s reason=%s"), *GetName(), *OldState, *GetStateName(), *LastSnapshot.MainClip.ToString(), *Reason);
}

FString AMorphCharacter::GetStateName() const
{
    switch (ControlState)
    {
    case EMorphControlState::Locomotion: return TEXT("Locomotion");
    case EMorphControlState::Action: return TEXT("Action");
    case EMorphControlState::Jump: return TEXT("Jump");
    case EMorphControlState::Blink: return TEXT("Blink");
    case EMorphControlState::Channel: return TEXT("Channel");
    case EMorphControlState::Charge: return TEXT("Charge");
    case EMorphControlState::Uplink: return TEXT("Uplink");
    case EMorphControlState::Stun: return TEXT("Stun");
    case EMorphControlState::Sleep: return TEXT("Sleep");
    case EMorphControlState::Knockup: return TEXT("Knockup");
    case EMorphControlState::Prone: return TEXT("Prone");
    case EMorphControlState::Dead: return TEXT("Dead");
    case EMorphControlState::Respawn: return TEXT("Respawn");
    case EMorphControlState::Manual: return TEXT("Manual");
    default: return TEXT("Unknown");
    }
}

FString AMorphCharacter::GetCameraModeName() const
{
    switch (CameraMode)
    {
    case EMorphCameraMode::ThirdPerson: return TEXT("Third");
    case EMorphCameraMode::Front: return TEXT("Front");
    case EMorphCameraMode::Side: return TEXT("Side");
    case EMorphCameraMode::TopDown: return TEXT("TopDown");
    case EMorphCameraMode::Face: return TEXT("Face");
    default: return TEXT("Third");
    }
}

bool AMorphCharacter::RequestClip(const FName Id)
{
    UMorphAnimInstance* Anim = GetMorphAnim();
    if (!Anim) return false;
    if (Id == TEXT("dialogue"))
    {
        PlayDialogue();
        return Anim->GetSequence(Id) != nullptr;
    }
    if (!Anim->RequestClip(Id))
    {
        return false;
    }
    if (Id == TEXT("deploy")) RestoreProps();
    if (DialogueAudio->IsPlaying())
    {
        DialogueAudio->Stop();
    }
    LastDirectClip = Id;
    bDirectClip = true;
    SetControlState(EMorphControlState::Manual, TEXT("browser:") + Id.ToString());
    bDirectClip = true;
    return true;
}

void AMorphCharacter::PlayDialogue()
{
    if (!CanFullBodyAction() || bSilenced)
    {
        return;
    }
    UMorphAnimInstance* Anim = GetMorphAnim();
    if (!Anim)
    {
        return;
    }
    Anim->StopUpper();
    Anim->ClearFaceOverrides();
    if (Anim->RequestClip(TEXT("dialogue"), .2f))
    {
        SetControlState(EMorphControlState::Action, TEXT("dialogue"));
        SetCameraMode(EMorphCameraMode::Face);
        if (DialogueWave)
        {
            DialogueAudio->Stop();
            DialogueAudio->Play(0.0f);
        }
    }
}

bool AMorphCharacter::IsDialoguePlaying() const
{
    return DialogueAudio && DialogueAudio->IsPlaying();
}

void AMorphCharacter::ResetShowcase()
{
    DialogueAudio->Stop();
    bDead = bRooted = bSilenced = bDisarmed = bStasis = bWounded = false;
    bWaitingTakeoff = bAnalogDrive = bSprinting = false;
    bDirectClip = false;
    DriveSpeed = KeyboardForward = KeyboardRight = 0.0f;
    GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(InitialLocation, false, nullptr, ETeleportType::TeleportPhysics);
    SetActorRotation(FRotator::ZeroRotator);
    GetMesh()->SetVisibility(true);
    RestoreProps();
    if (UMorphAnimInstance* Anim = GetMorphAnim())
    {
        Anim->ResetRuntime();
        Anim->RequestClip(TEXT("idle_relaxed"), 0.0f);
        Anim->ResetFace();
        Anim->SetAim(0, 0, false);
    }
    AimYaw = AimPitch = 0.0f;
    FallImpactSpeed = 0.0f;
    PreviousHorizontalSpeed = 0.0f;
    SetEyeLook(0, 0, 0, 0);
    SetTeam(0);
    SetLOD(0);
    CameraOrbitYaw = 0.0f;
    SetCameraMode(EMorphCameraMode::ThirdPerson);
    SetControlState(EMorphControlState::Locomotion, TEXT("reset"));
}

void AMorphCharacter::SetCameraMode(const EMorphCameraMode Mode)
{
    CameraMode = Mode;
    CameraOrbitPitch = 0.0f;
}

void AMorphCharacter::CycleCamera()
{
    SetCameraMode(static_cast<EMorphCameraMode>((static_cast<uint8>(CameraMode) + 1) % 5));
}

void AMorphCharacter::SetTeam(const int32 TeamIndex)
{
    Team = TeamIndex == 0 ? 0 : 1;
    const FLinearColor Accent = Team == 0 ? FLinearColor(.02f, .8f, 1.0f) : FLinearColor(1.0f, .43f, .035f);
    const TArray<USkinnedMeshComponent*> Meshes = { GetMesh() };
    for (USkinnedMeshComponent* Mesh : Meshes)
    {
        if (!Mesh || !Mesh->GetSkinnedAsset()) continue;
        for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
        {
            if (UMaterialInstanceDynamic* Material = Mesh->CreateAndSetMaterialInstanceDynamic(Index))
            {
                Material->SetVectorParameterValue(TEXT("TeamAccent"), Accent);
                Material->SetVectorParameterValue(TEXT("TeamColor"), Accent);
                Material->SetVectorParameterValue(TEXT("AccentColor"), Accent);
                Material->SetScalarParameterValue(TEXT("TeamIndex"), static_cast<float>(Team));
                Material->SetScalarParameterValue(TEXT("Team"), static_cast<float>(Team));
            }
        }
    }
    if (DeployedBeacon)
    {
        for (int32 Index = 0; Index < DeployedBeacon->GetNumMaterials(); ++Index)
        {
            if (UMaterialInstanceDynamic* Material = DeployedBeacon->CreateAndSetMaterialInstanceDynamic(Index))
            {
                Material->SetVectorParameterValue(TEXT("TeamAccent"), Accent);
                Material->SetVectorParameterValue(TEXT("TeamColor"), Accent);
                Material->SetVectorParameterValue(TEXT("AccentColor"), Accent);
                Material->SetScalarParameterValue(TEXT("TeamIndex"), static_cast<float>(Team));
                Material->SetScalarParameterValue(TEXT("Team"), static_cast<float>(Team));
            }
        }
    }
    TeamBadge->SetText(FText::FromString(Team == 0 ? TEXT("I") : TEXT("II")));
    TeamBadge->SetTextRenderColor(Accent.ToFColor(true));
}

void AMorphCharacter::SetLOD(const int32 LODIndex)
{
    ForcedLOD = FMath::Clamp(LODIndex, 0, 2);
    GetMesh()->SetForcedLOD(ForcedLOD + 1);
}

void AMorphCharacter::ToggleSkeletonDebug()
{
    bSkeletonDebug = !bSkeletonDebug;
    GetMesh()->SetDrawDebugSkeleton(bSkeletonDebug);
}

void AMorphCharacter::SetAim(const float Yaw, const float Pitch)
{
    AimYaw = FMath::Clamp(Yaw, -60.0f, 60.0f);
    AimPitch = FMath::Clamp(Pitch, -35.0f, 35.0f);
    if (UMorphAnimInstance* Anim = GetMorphAnim()) Anim->SetAim(AimYaw, AimPitch, true);
}

void AMorphCharacter::SetEyeLook(const float LeftYaw, const float LeftPitch, const float RightYaw, const float RightPitch)
{
    EyeLeftYaw = FMath::Clamp(LeftYaw, -25.0f, 25.0f);
    EyeLeftPitch = FMath::Clamp(LeftPitch, -18.0f, 18.0f);
    EyeRightYaw = FMath::Clamp(RightYaw, -25.0f, 25.0f);
    EyeRightPitch = FMath::Clamp(RightPitch, -18.0f, 18.0f);
    if (UMorphAnimInstance* Anim = GetMorphAnim()) Anim->SetEyeLook(EyeLeftYaw, EyeLeftPitch, EyeRightYaw, EyeRightPitch);
}

void AMorphCharacter::SetLocomotionDrive(const float Speed, const float DirectionDegrees)
{
    if (!CanFullBodyAction() || bRooted) return;
    DriveSpeed = FMath::Clamp(Speed, 0.0f, 650.0f);
    DriveDirection = FMath::Clamp(DirectionDegrees, -180.0f, 180.0f);
    bAnalogDrive = true;
    if (ControlState == EMorphControlState::Manual) SetControlState(EMorphControlState::Locomotion, TEXT("analog_drive"));
}

void AMorphCharacter::StopLocomotionDrive()
{
    DriveSpeed = 0.0f;
    KeyboardForward = KeyboardRight = 0.0f;
    bAnalogDrive = true;
}

void AMorphCharacter::RequestTurn(const float Degrees)
{
    if (!CanFullBodyAction() || GetCharacterMovement()->IsFalling()) return;
    const FName Clip = FMath::Abs(Degrees) >= 135.0f ? (Degrees < 0 ? FName(TEXT("pivot_l180")) : FName(TEXT("pivot_r180"))) : (Degrees < 0 ? FName(TEXT("turn_l90")) : FName(TEXT("turn_r90")));
    if (GetMorphAnim() && GetMorphAnim()->RequestClip(Clip, .16f))
    {
        SetControlState(EMorphControlState::Action, TEXT("facing_request"));
    }
}

void AMorphCharacter::RequestJump()
{
    if (!CanFullBodyAction() || bRooted || GetCharacterMovement()->IsFalling()) return;
    if (GetMorphAnim() && GetMorphAnim()->RequestClip(TEXT("jump_start"), .12f, TEXT("jump_air")))
    {
        bWaitingTakeoff = true;
        SetControlState(EMorphControlState::Jump, TEXT("jump_start"));
    }
}

void AMorphCharacter::RequestDash(const FName Direction)
{
    if (!CanFullBodyAction() || bRooted || GetCharacterMovement()->IsFalling()) return;
    FString S = Direction.ToString();
    if (!S.StartsWith(TEXT("dash_"))) S = TEXT("dash_") + S;
    if (S != TEXT("dash_f") && S != TEXT("dash_b") && S != TEXT("dash_l") && S != TEXT("dash_r")) S = TEXT("dash_f");
    GetCharacterMovement()->StopMovementImmediately();
    if (GetMorphAnim() && GetMorphAnim()->RequestClip(FName(*S), .08f))
    {
        SetControlState(EMorphControlState::Action, TEXT("capsule_root_dash"));
    }
}

void AMorphCharacter::RequestBlink()
{
    if (!CanFullBodyAction() || bRooted || bSilenced) return;
    if (GetMorphAnim() && GetMorphAnim()->RequestClip(TEXT("blink_out"), .1f))
    {
        SetControlState(EMorphControlState::Blink, TEXT("blink_out"));
    }
}

void AMorphCharacter::RequestMelee(const int32 Index)
{
    if (!CanFullBodyAction() || bDisarmed) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(FName(*FString::Printf(TEXT("melee_%d"), FMath::Clamp(Index, 1, 3))), .12f))
    {
        SetControlState(EMorphControlState::Action, TEXT("melee"));
    }
}

void AMorphCharacter::RequestRanged(const bool bBurst)
{
    if (!CanUpperBodyAction() || bDisarmed) return;
    GetMorphAnim()->RequestUpperClip(bBurst ? TEXT("ranged_burst") : TEXT("ranged_fire"));
}

void AMorphCharacter::RequestReload()
{
    if (!CanFullBodyAction() || bDisarmed) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("reload"), .16f)) SetControlState(EMorphControlState::Action, TEXT("reload"));
}

void AMorphCharacter::RequestCast(const FName CastId)
{
    if (bSilenced) return;
    if (CastId == TEXT("cast_directional"))
    {
        if (CanUpperBodyAction()) GetMorphAnim()->RequestUpperClip(CastId);
        return;
    }
    if (!CanFullBodyAction()) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(CastId, .15f)) SetControlState(EMorphControlState::Action, *CastId.ToString());
}

void AMorphCharacter::RequestDeploy()
{
    if (!CanFullBodyAction() || bDisarmed) return;
    RestoreProps();
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("deploy"), .16f)) SetControlState(EMorphControlState::Action, TEXT("deploy"));
}

void AMorphCharacter::StartChannel()
{
    if (!CanFullBodyAction() || bSilenced) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("channel_start"), .14f, TEXT("channel_loop"))) SetControlState(EMorphControlState::Channel, TEXT("channel_start"));
}

void AMorphCharacter::FinishChannel()
{
    if (ControlState != EMorphControlState::Channel) return;
    if (GetMorphAnim()->RequestClip(TEXT("channel_end"), .12f)) SetControlState(EMorphControlState::Action, TEXT("channel_finish"));
}

void AMorphCharacter::InterruptChannel()
{
    if (ControlState != EMorphControlState::Channel) return;
    if (GetMorphAnim()->RequestClip(TEXT("channel_interrupt"), .07f)) SetControlState(EMorphControlState::Action, TEXT("channel_interrupt_arbitrary"));
}

void AMorphCharacter::StartCharge()
{
    if (!CanFullBodyAction() || bSilenced) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("charge_start"), .14f, TEXT("charge_hold"))) SetControlState(EMorphControlState::Charge, TEXT("charge_start"));
}

void AMorphCharacter::ReleaseCharge()
{
    if (ControlState != EMorphControlState::Charge) return;
    if (GetMorphAnim()->RequestClip(TEXT("charge_release"), .08f)) SetControlState(EMorphControlState::Action, TEXT("charge_release"));
}

void AMorphCharacter::CancelCharge()
{
    if (ControlState != EMorphControlState::Charge) return;
    if (GetMorphAnim()->RequestClip(TEXT("charge_cancel"), .08f)) SetControlState(EMorphControlState::Action, TEXT("charge_cancel"));
}

void AMorphCharacter::StartUplink()
{
    if (!CanFullBodyAction() || bSilenced || bRooted) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("uplink_start"), .16f, TEXT("uplink_loop"))) SetControlState(EMorphControlState::Uplink, TEXT("uplink_start"));
}

void AMorphCharacter::FinishUplink()
{
    if (ControlState != EMorphControlState::Uplink) return;
    if (GetMorphAnim()->RequestClip(TEXT("uplink_end"), .1f)) SetControlState(EMorphControlState::Action, TEXT("uplink_finish"));
}

void AMorphCharacter::CancelUplink()
{
    if (ControlState != EMorphControlState::Uplink) return;
    if (GetMorphAnim()->RequestClip(TEXT("uplink_cancel"), .08f)) SetControlState(EMorphControlState::Action, TEXT("uplink_cancel"));
}

void AMorphCharacter::ApplyHit(const FName Direction)
{
    if (bDead || bStasis || ControlState == EMorphControlState::Prone || ControlState == EMorphControlState::Sleep) return;
    FString S = Direction.ToString();
    if (!S.StartsWith(TEXT("hit_"))) S = TEXT("hit_") + S;
    if (S != TEXT("hit_f") && S != TEXT("hit_b") && S != TEXT("hit_l") && S != TEXT("hit_r")) S = TEXT("hit_f");
    GetMorphAnim()->RequestHit(FName(*S));
}

void AMorphCharacter::StartStun()
{
    if (bDead || bStasis) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("stun_start"), .1f, TEXT("stun_loop"))) SetControlState(EMorphControlState::Stun, TEXT("stun_start"));
}

void AMorphCharacter::EndStun()
{
    if (ControlState != EMorphControlState::Stun) return;
    if (GetMorphAnim()->RequestClip(TEXT("stun_end"), .12f)) SetControlState(EMorphControlState::Action, TEXT("stun_end"));
}

void AMorphCharacter::StartSleep()
{
    if (bDead || bStasis) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("sleep_start"), .15f, TEXT("sleep_loop"))) SetControlState(EMorphControlState::Sleep, TEXT("sleep_start"));
}

void AMorphCharacter::EndSleep()
{
    if (ControlState != EMorphControlState::Sleep) return;
    if (GetMorphAnim()->RequestClip(TEXT("sleep_end"), .12f)) SetControlState(EMorphControlState::Action, TEXT("sleep_end"));
}

void AMorphCharacter::Knockup()
{
    if (bDead || bStasis) return;
    GetMorphAnim()->StopUpper();
    if (GetMorphAnim()->RequestClip(TEXT("knockup_start"), .08f, TEXT("knockup_air")))
    {
        GetCharacterMovement()->Launch(FVector(0, 0, 600));
        SetControlState(EMorphControlState::Knockup, TEXT("knockup"));
    }
}

void AMorphCharacter::Knockback()
{
    if (bDead || bStasis) return;
    if (GetMorphAnim()->RequestClip(TEXT("knockback"), .08f))
    {
        GetCharacterMovement()->Launch(-GetActorForwardVector() * 250.0);
        SetControlState(EMorphControlState::Action, TEXT("knockback"));
    }
}

void AMorphCharacter::Knockdown(const bool bFront)
{
    if (bDead || bStasis) return;
    GetMorphAnim()->StopUpper();
    const FName Start = bFront ? FName(TEXT("knockdown_front")) : FName(TEXT("knockdown_back"));
    const FName Prone = bFront ? FName(TEXT("prone_front")) : FName(TEXT("prone_back"));
    if (GetMorphAnim()->RequestClip(Start, .1f, Prone)) SetControlState(EMorphControlState::Prone, TEXT("knockdown"));
}

void AMorphCharacter::GetUp()
{
    if (ControlState != EMorphControlState::Prone) return;
    const bool bFront = LastSnapshot.MainClip == TEXT("prone_front") || LastSnapshot.MainClip == TEXT("knockdown_front");
    if (GetMorphAnim()->RequestClip(bFront ? TEXT("getup_front") : TEXT("getup_back"), .12f)) SetControlState(EMorphControlState::Action, TEXT("getup"));
}

void AMorphCharacter::Die(const bool bFront)
{
    if (bDead) return;
    bDead = true;
    DialogueAudio->Stop();
    GetCharacterMovement()->StopMovementImmediately();
    GetCharacterMovement()->SetMovementMode(MOVE_None);
    GetMorphAnim()->StopUpper(.04f);
    GetMorphAnim()->SetAim(AimYaw, AimPitch, false);
    GetMesh()->HideBoneByName(TEXT("cell"), PBO_None);
    GetMesh()->HideBoneByName(TEXT("beacon"), PBO_None);
    if (GetMorphAnim()->RequestClip(bFront ? TEXT("death_front") : TEXT("death_back"), .08f, bFront ? TEXT("dead_front") : TEXT("dead_back")))
    {
        SetControlState(EMorphControlState::Dead, TEXT("death_once"));
    }
}

void AMorphCharacter::RestoreProps()
{
    GetMesh()->UnHideBoneByName(TEXT("cell"));
    GetMesh()->UnHideBoneByName(TEXT("beacon"));
    if (DeployedBeacon) DeployedBeacon->SetVisibility(false);
    PropState = TEXT("cell:seated beacon:stowed");
}

void AMorphCharacter::Respawn()
{
    if (!bDead) return;
    bDead = false;
    GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    GetMesh()->SetVisibility(true);
    RestoreProps();
    if (GetMorphAnim()->RequestClip(TEXT("respawn"), .1f)) SetControlState(EMorphControlState::Respawn, TEXT("respawn_restore_living_props"));
}

void AMorphCharacter::SetRooted(const bool bValue)
{
    bRooted = bValue;
    if (bRooted)
    {
        DriveSpeed = KeyboardForward = KeyboardRight = 0.0f;
        FVector Velocity = GetCharacterMovement()->Velocity;
        Velocity.X = Velocity.Y = 0.0;
        GetCharacterMovement()->Velocity = Velocity;
        if (ControlState == EMorphControlState::Action && LastSnapshot.MainClip.ToString().StartsWith(TEXT("dash_")))
        {
            if (GetMorphAnim() && GetMorphAnim()->RequestClip(TEXT("idle_combat"), .08f))
            {
                SetControlState(EMorphControlState::Locomotion, TEXT("root_cancels_dash"));
            }
        }
    }
}

void AMorphCharacter::SetSilenced(const bool bValue)
{
    bSilenced = bValue;
    if (bSilenced && ControlState == EMorphControlState::Channel) InterruptChannel();
    if (bSilenced && ControlState == EMorphControlState::Charge) CancelCharge();
    if (bSilenced && ControlState == EMorphControlState::Uplink) CancelUplink();
}

void AMorphCharacter::SetDisarmed(const bool bValue)
{
    bDisarmed = bValue;
    if (bDisarmed) GetMorphAnim()->StopUpper();
}

void AMorphCharacter::SetStasis(const bool bValue)
{
    bStasis = bValue;
    if (GetMorphAnim()) GetMorphAnim()->SetStasis(bValue);
    if (!bDead) GetCharacterMovement()->SetMovementMode(bValue ? MOVE_None : MOVE_Walking);
}

void AMorphCharacter::SetWounded(const bool bValue)
{
    bWounded = bValue;
}

void AMorphCharacter::UpdateMovement(const float DeltaSeconds)
{
    if (bDead || bStasis || ControlState == EMorphControlState::Stun || ControlState == EMorphControlState::Sleep || ControlState == EMorphControlState::Prone || ControlState == EMorphControlState::Knockup)
    {
        return;
    }
    if (ControlState == EMorphControlState::Action || ControlState == EMorphControlState::Respawn || ControlState == EMorphControlState::Channel || ControlState == EMorphControlState::Charge || ControlState == EMorphControlState::Uplink || ControlState == EMorphControlState::Blink)
    {
        return;
    }
    if (!bRooted)
    {
        if (bAnalogDrive)
        {
            const float Radians = FMath::DegreesToRadians(DriveDirection);
            const FVector Direction = GetActorForwardVector() * FMath::Cos(Radians) + GetActorRightVector() * FMath::Sin(Radians);
            GetCharacterMovement()->MaxWalkSpeed = FMath::Max(1.0f, DriveSpeed);
            if (DriveSpeed > 0.0f) AddMovementInput(Direction, 1.0f);
        }
        else
        {
            GetCharacterMovement()->MaxWalkSpeed = bSprinting ? 650.0f : 400.0f;
            if (KeyboardForward != 0.0f) AddMovementInput(GetActorForwardVector(), KeyboardForward);
            if (KeyboardRight != 0.0f) AddMovementInput(GetActorRightVector(), KeyboardRight);
        }
    }
}

void AMorphCharacter::UpdateAutomaticAnimation(const bool bDriveLocomotion)
{
    UMorphAnimInstance* Anim = GetMorphAnim();
    if (!Anim || bDirectClip) return;
    const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
    if (ControlState != EMorphControlState::Locomotion)
    {
        if ((ControlState == EMorphControlState::Action || ControlState == EMorphControlState::Respawn || ControlState == EMorphControlState::Blink) && Snapshot.bMainComplete)
        {
            SetControlState(EMorphControlState::Locomotion, TEXT("action_complete"));
            if (!bDriveLocomotion)
            {
                Anim->RequestClip(bWounded ? TEXT("idle_wounded") : TEXT("idle_relaxed"), .18f);
                return;
            }
        }
        else
        {
            return;
        }
    }
    if (!bDriveLocomotion) return;

    const bool bFalling = GetCharacterMovement()->IsFalling();
    if (bFalling && ControlState != EMorphControlState::Jump)
    {
        const FName FallClip = GetCharacterMovement()->Velocity.Z < -350.0f ? FName(TEXT("fall")) : FName(TEXT("jump_air"));
        if (Snapshot.MainClip != FallClip) Anim->RequestClip(FallClip, .15f);
        return;
    }
    const FString Current = Snapshot.MainClip.ToString();
    const bool bTransitionPlaying = (Current == TEXT("start_f") || Current == TEXT("stop_f") || Current == TEXT("jump_land") || Current == TEXT("land_heavy")) && !Snapshot.bMainComplete;
    if (bTransitionPlaying) return;

    const float Speed = GetVelocity().Size2D();
    if (Speed > 25.0f && PreviousHorizontalSpeed <= 25.0f && !bFalling && Snapshot.MainClip != TEXT("start_f"))
    {
        Anim->RequestClip(TEXT("start_f"), .1f);
        PreviousHorizontalSpeed = Speed;
        return;
    }
    if (Speed < 12.0f && PreviousHorizontalSpeed > 40.0f && !bFalling && Snapshot.MainClip != TEXT("stop_f"))
    {
        Anim->RequestClip(TEXT("stop_f"), .1f);
        PreviousHorizontalSpeed = Speed;
        return;
    }
    PreviousHorizontalSpeed = Speed;

    FName Desired = bWounded ? FName(TEXT("idle_wounded")) : FName(TEXT("idle_relaxed"));
    float NominalSpeed = 0.0f;
    if (Speed >= 20.0f && !bFalling)
    {
        const FVector LocalVelocity = GetActorTransform().InverseTransformVectorNoScale(GetVelocity());
        float Angle = FMath::RadiansToDegrees(FMath::Atan2(LocalVelocity.Y, LocalVelocity.X));
        if (Angle < 0.0f) Angle += 360.0f;
        static const TCHAR* Directions[8] = { TEXT("f"), TEXT("fr"), TEXT("r"), TEXT("br"), TEXT("b"), TEXT("bl"), TEXT("l"), TEXT("fl") };
        const int32 DirectionIndex = FMath::RoundToInt(Angle / 45.0f) % 8;
        if (Speed > 530.0f && DirectionIndex == 0)
        {
            Desired = TEXT("sprint_f");
            NominalSpeed = 650.0f;
        }
        else
        {
            const bool bWalk = Speed < 260.0f;
            Desired = FName(*FString::Printf(TEXT("%s_%s"), bWalk ? TEXT("walk") : TEXT("run"), Directions[DirectionIndex]));
            NominalSpeed = bWalk ? 150.0f : 400.0f;
        }
    }
    if (Snapshot.MainClip != Desired && (Snapshot.bMainComplete || Snapshot.MainClip == TEXT("idle_relaxed") || Snapshot.MainClip == TEXT("idle_wounded") || Snapshot.MainClip.ToString().StartsWith(TEXT("walk_")) || Snapshot.MainClip.ToString().StartsWith(TEXT("run_")) || Snapshot.MainClip == TEXT("sprint_f") || Snapshot.MainClip == TEXT("jump_air") || Snapshot.MainClip == TEXT("fall") || Snapshot.MainClip == TEXT("start_f") || Snapshot.MainClip == TEXT("stop_f")))
    {
        Anim->RequestClip(Desired, .18f);
    }
    Anim->SetLocomotionRate(NominalSpeed > 0.0f ? FMath::Clamp(Speed / NominalSpeed, .5f, 1.5f) : 1.0f);
}

void AMorphCharacter::Landed(const FHitResult& Hit)
{
    Super::Landed(Hit);
    if (bDead || ControlState == EMorphControlState::Prone || ControlState == EMorphControlState::Sleep) return;
    if (ControlState == EMorphControlState::Knockup)
    {
        Knockdown(true);
        return;
    }
    if (GetMorphAnim()->RequestClip(FallImpactSpeed < -700.0f ? TEXT("land_heavy") : TEXT("jump_land"), .08f))
    {
        SetControlState(EMorphControlState::Action, TEXT("landed"));
    }
}

void AMorphCharacter::CacheRestFootHeights()
{
    bRestHeightsCached = false;
    const USkeletalMesh* SkeletalMesh = GetMesh()->GetSkeletalMeshAsset();
    if (!SkeletalMesh || !SkeletalMesh->GetSkeleton()) return;
    const FReferenceSkeleton& Ref = SkeletalMesh->GetRefSkeleton();
    const TArray<FTransform>& Local = Ref.GetRefBonePose();
    TArray<FTransform> Component;
    Component.SetNum(Local.Num());
    for (int32 Index = 0; Index < Local.Num(); ++Index)
    {
        const int32 Parent = Ref.GetParentIndex(Index);
        Component[Index] = Parent == INDEX_NONE ? Local[Index] : Local[Index] * Component[Parent];
    }
    for (int32 Leg = 0; Leg < 2; ++Leg)
    {
        const int32 Bone = Ref.FindBoneIndex(Leg == 0 ? FName(TEXT("foot_L")) : FName(TEXT("foot_R")));
        if (Component.IsValidIndex(Bone))
        {
            RestAnkleHeight[Leg] = FMath::Max(0.0, Component[Bone].GetLocation().Z);
            bRestHeightsCached = true;
            UE_LOG(LogMorphRig, Log, TEXT("MR_FOOT_REST leg=%d ankle_cm=%.3f"), Leg, RestAnkleHeight[Leg]);
        }
    }
}

void AMorphCharacter::UpdateGroundCompensation(const float DeltaSeconds)
{
    const UMorphAnimInstance* Anim = GetMorphAnim();
    const float CaptureStep = Anim ? Anim->GetCaptureStepSeconds() : 0.0f;
    const float StepDelta = CaptureStep > 0.0f ? CaptureStep : DeltaSeconds;
    const FHitResult& Floor = GetCharacterMovement()->CurrentFloor.HitResult;
    const FString Surface = Floor.Component.IsValid() ? Floor.Component->GetName() : TEXT("");
    const bool bSupportedFloor = Floor.bBlockingHit && (Surface == TEXT("Floor") || Surface == TEXT("Ramp20Degrees") || Surface.StartsWith(TEXT("Step20cm_")));
    const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const float DesiredOffset = !GetCharacterMovement()->IsFalling() && bSupportedFloor
        ? FMath::Min(0.0f, Floor.ImpactPoint.Z - (GetCapsuleComponent()->GetComponentLocation().Z - HalfHeight))
        : 0.0f;
    MeshGroundOffset = FMath::FInterpTo(MeshGroundOffset, DesiredOffset, StepDelta, 18.0f);
    GetMesh()->SetRelativeLocation(FVector(0.0, 0.0, -HalfHeight + MeshGroundOffset));
}

void AMorphCharacter::UpdateGroundIK()
{
    FMorphGroundData Ground;
    UMorphAnimInstance* Anim = GetMorphAnim();
    if (!Anim) return;
    const FString Clip = Anim->GetSnapshot().MainClip.ToString();
    const FQuat ActorRotation = GetActorRotation().Quaternion();
    const bool bNewContactContext = FName(*Clip) != LastGroundClip || (GetActorLocation() - LastGroundLocation).SizeSquared2D() > 30.0f * 30.0f || ActorRotation.AngularDistance(LastGroundRotation) > FMath::DegreesToRadians(15.0f);
    LastGroundClip = FName(*Clip);
    LastGroundLocation = GetActorLocation();
    LastGroundRotation = ActorRotation;
    if (bNewContactContext)
    {
        Anim->SetGroundData(FMorphGroundData());
        return;
    }
    const bool bPoseDisablesIK = Clip.StartsWith(TEXT("death_")) || Clip.StartsWith(TEXT("dead_")) || Clip.StartsWith(TEXT("prone_")) || Clip.StartsWith(TEXT("knockdown_")) || Clip.StartsWith(TEXT("knockup_")) || Clip.StartsWith(TEXT("getup_")) || Clip.StartsWith(TEXT("dash_")) || Clip.StartsWith(TEXT("sleep_")) || Clip == TEXT("jump_air") || Clip == TEXT("fall") || Clip == TEXT("knockback");
    const bool bAllowed = !bPoseDisablesIK && !GetCharacterMovement()->IsFalling() && !bDead && !bStasis && ControlState != EMorphControlState::Prone && ControlState != EMorphControlState::Sleep && ControlState != EMorphControlState::Knockup && ControlState != EMorphControlState::Dead;
    Ground.bEnabled = bAllowed && bRestHeightsCached;
    if (!Ground.bEnabled)
    {
        Anim->SetGroundData(Ground);
        return;
    }
    float LowestOffset = 0.0f;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphFootTrace), false, this);
    for (TActorIterator<AMorphCharacter> It(GetWorld()); It; ++It) Params.AddIgnoredActor(*It);
    const FVector Forward = GetActorForwardVector();
    const FVector Right = GetActorRightVector();
    const float Offsets[] = { 0.0f, 12.0f, -12.0f };
    for (int32 Leg = 0; Leg < 2; ++Leg)
    {
        const FName BoneName = Leg == 0 ? FName(TEXT("foot_L")) : FName(TEXT("foot_R"));
        const int32 BoneIndex = GetMesh()->GetBoneIndex(BoneName);
        const FName ThighName = Leg == 0 ? FName(TEXT("thigh_L")) : FName(TEXT("thigh_R"));
        const FName ShinName = Leg == 0 ? FName(TEXT("shin_L")) : FName(TEXT("shin_R"));
        if (BoneIndex == INDEX_NONE || GetMesh()->GetBoneIndex(ThighName) == INDEX_NONE || GetMesh()->GetBoneIndex(ShinName) == INDEX_NONE) continue;
        const FVector Hip = GetMesh()->GetBoneTransform(ThighName).GetLocation();
        const FVector Knee = GetMesh()->GetBoneTransform(ShinName).GetLocation();
        const FVector Foot = GetMesh()->GetBoneTransform(BoneIndex).GetLocation();
        const double Reach = FVector::Distance(Hip, Knee) + FVector::Distance(Knee, Foot);
        const double MaxReach = Reach * .999;
        const double MaxReachSquared = MaxReach * MaxReach;
        if (MaxReach < .01) continue;
        FVector BestPoint = Foot;
        FHitResult BestHit;
        double BestDrop = 0.0;
        float BestScore = TNumericLimits<float>::Max();
        for (const float Along : Offsets)
        {
            for (const float Across : Offsets)
            {
                const FVector Point = Foot + Forward * Along + Right * Across;
                FHitResult Hit;
                if (!GetWorld()->LineTraceSingleByChannel(Hit, Point + FVector(0, 0, 42), Point - FVector(0, 0, 58), ECC_Visibility, Params)) continue;
                const FString Surface = Hit.Component.IsValid() ? Hit.Component->GetName() : TEXT("");
                if (Surface != TEXT("Floor") && Surface != TEXT("Ramp20Degrees") && !Surface.StartsWith(TEXT("Step20cm_"))) continue;
                if (Hit.ImpactNormal.Z < FMath::Cos(FMath::DegreesToRadians(20.0f))) continue;
                const float SoleHeight = Foot.Z - Hit.ImpactPoint.Z;
                if (SoleHeight > RestAnkleHeight[Leg] + 3.0f || SoleHeight < RestAnkleHeight[Leg] - 22.0f) continue;
                const double HorizontalSquared = FVector::DistSquared2D(Hip, Point);
                if (HorizontalSquared > MaxReachSquared) continue;
                const double TargetZ = Hit.ImpactPoint.Z + RestAnkleHeight[Leg];
                const double Drop = Hip.Z - TargetZ - FMath::Sqrt(FMath::Max(0.0, MaxReachSquared - HorizontalSquared));
                if (Drop > 20.0) continue;
                const float Score = FMath::Abs(TargetZ - Foot.Z) * .20 + FMath::Max(0.0, Drop) * 4.0;
                if (Score >= BestScore) continue;
                BestScore = Score;
                BestPoint = Point;
                BestPoint.Z = TargetZ;
                BestHit = Hit;
                BestDrop = Drop;
            }
        }
        if (BestScore == TNumericLimits<float>::Max()) continue;
        const float Offset = FMath::Clamp(BestPoint.Z - Foot.Z, -20.0, 20.0);
        BestPoint.Z = Foot.Z + Offset;
        Ground.Feet[Leg].bValid = true;
        Ground.Feet[Leg].EffectorComponent = GetMesh()->GetComponentTransform().InverseTransformPosition(BestPoint);
        Ground.Feet[Leg].NormalComponent = GetMesh()->GetComponentTransform().InverseTransformVectorNoScale(BestHit.ImpactNormal).GetSafeNormal();
        Ground.Feet[Leg].Offset = Offset;
        LowestOffset = FMath::Min(LowestOffset, FMath::Min(Offset, static_cast<float>(-BestDrop)));
        if (GFrameCounter % 30 == 0 && (Anim->GetSnapshot().MainClip == TEXT("walk_f") || Anim->GetSnapshot().MainClip == TEXT("stop_f")))
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_CONTACT_CHOICE leg=%d foot=%s target=%s local_target=%s floor_z=%.3f ankle=%.3f drop=%.3f reach=%.3f pelvis=%.3f mesh=%s"), Leg, *Foot.ToString(), *BestPoint.ToString(), *Ground.Feet[Leg].EffectorComponent.ToString(), BestHit.ImpactPoint.Z, RestAnkleHeight[Leg], BestDrop, Reach, Ground.PelvisOffset, *GetMesh()->GetComponentTransform().ToString());
        }
    }
    Ground.PelvisOffset = FMath::Clamp(LowestOffset, -20.0, 0.0);
    Anim->SetGroundData(Ground);
}

void AMorphCharacter::UpdateCamera(const float DeltaSeconds)
{
    if (!ShowcaseCamera) return;
    const FVector Actor = GetActorLocation();
    const FRotator YawRotation(0.0, GetActorRotation().Yaw + CameraOrbitYaw, 0.0);
    const FVector Forward = YawRotation.Vector();
    const FVector Right = FRotationMatrix(YawRotation).GetScaledAxis(EAxis::Y);
    FVector Focus = Actor + FVector(0, 0, 35);
    FVector Location;
    switch (CameraMode)
    {
    case EMorphCameraMode::ThirdPerson:
        Focus = Actor + FVector(0, 0, 30);
        Location = Focus - Forward * 330.0 + FVector(0, 0, 115 + CameraOrbitPitch * 80);
        break;
    case EMorphCameraMode::Front:
        Location = Actor + Forward * 330.0 + FVector(0, 0, 30 + CameraOrbitPitch * 60);
        Focus = Actor + FVector(0, 0, 15);
        break;
    case EMorphCameraMode::Side:
        Location = Actor + Right * 330.0 + FVector(0, 0, 25 + CameraOrbitPitch * 60);
        Focus = Actor + FVector(0, 0, 10);
        break;
    case EMorphCameraMode::TopDown:
        Location = Actor - Forward * 900.0 + FVector(0, 0, 1080);
        Focus = Actor + Forward * 45.0;
        break;
    case EMorphCameraMode::Face:
    {
        const int32 Head = GetMesh()->GetBoneIndex(TEXT("head"));
        Focus = Head == INDEX_NONE ? Actor + FVector(0, 0, 65) : GetMesh()->GetBoneTransform(Head).GetLocation() + GetActorForwardVector() * 5.0 + FVector(0, 0, 14);
        Location = Focus + Forward * 52.0 + FVector(0, 0, 4 + CameraOrbitPitch * 15);
        break;
    }
    }
    ShowcaseCamera->SetWorldLocationAndRotation(Location, (Focus - Location).Rotation());
}

void AMorphCharacter::TriggerEffect(const FName EventName)
{
    EffectRemaining = EventName == TEXT("MuzzleFire") ? .075f : .16f;
    EffectMesh->SetVisibility(true);
    const FVector Start = EffectMesh->GetComponentLocation();
    const FVector End = Start + GetActorForwardVector() * 500.0;
    DrawDebugLine(GetWorld(), Start, End, Team == 0 ? FColor::Cyan : FColor::Orange, false, EffectRemaining, 0, 1.4f);
}

void AMorphCharacter::UpdateEffect(const float DeltaSeconds)
{
    if (EffectRemaining > 0.0f)
    {
        EffectRemaining -= DeltaSeconds;
        if (EffectRemaining <= 0.0f) EffectMesh->SetVisibility(false);
    }
}

void AMorphCharacter::HandleMorphEvent(const FMorphRuntimeEvent& Event)
{
    LastNativeEvent = Event.EventName.ToString();
    UE_LOG(LogMorphRig, Log, TEXT("MR_EVENT actor=%s event=%s clip=%s time=%.6f traversal=%d"), *GetName(), *Event.EventName.ToString(), *Event.ClipId.ToString(), Event.ClipTime, Event.Traversal);
    if (Event.EventName == TEXT("MuzzleFire") || Event.EventName == TEXT("CastRelease") || Event.EventName == TEXT("ChargeRelease") || Event.EventName == TEXT("ChannelLoop"))
    {
        TriggerEffect(Event.EventName);
    }
    if (Event.EventName.ToString().StartsWith(TEXT("Cell")) || Event.EventName.ToString().StartsWith(TEXT("Deploy")))
    {
        PropState = Event.EventName.ToString();
    }
    if (Event.EventName == TEXT("DeployRelease") && Event.ClipId == TEXT("deploy") && DeployedBeacon)
    {
        DeployedBeacon->SetWorldTransform(GetMesh()->GetSocketTransform(TEXT("beacon"), RTS_World));
        DeployedBeacon->SetVisibility(true);
        GetMesh()->HideBoneByName(TEXT("beacon"), PBO_None);
        PropState = TEXT("beacon:deployed");
    }
    else if (Event.EventName == TEXT("Takeoff") && bWaitingTakeoff)
    {
        bWaitingTakeoff = false;
        Jump();
    }
    else if (Event.EventName == TEXT("TeleportOut"))
    {
        const FVector Destination = GetActorLocation() + GetActorForwardVector() * 400.0;
        GetMesh()->SetVisibility(false);
        SetActorLocation(Destination, true, nullptr, ETeleportType::TeleportPhysics);
        GetMorphAnim()->RequestClip(TEXT("blink_in"), .04f);
    }
    else if (Event.EventName == TEXT("TeleportIn"))
    {
        GetMesh()->SetVisibility(true);
    }
    else if (Event.EventName == TEXT("FacingCommit"))
    {
        float Angle = 0.0f;
        if (Event.ClipId == TEXT("turn_l90")) Angle = -90.0f;
        else if (Event.ClipId == TEXT("turn_r90")) Angle = 90.0f;
        else if (Event.ClipId == TEXT("pivot_l180")) Angle = -180.0f;
        else if (Event.ClipId == TEXT("pivot_r180")) Angle = 180.0f;
        FRotator Rotation = GetActorRotation();
        Rotation.Yaw = FRotator::NormalizeAxis(Rotation.Yaw + Angle);
        SetActorRotation(Rotation);
    }
    else if (Event.EventName == TEXT("Recovery") && ControlState == EMorphControlState::Action && Event.ClipId.ToString().StartsWith(TEXT("melee_")))
    {
        SetControlState(EMorphControlState::Locomotion, TEXT("melee_recovery_marker"));
    }
    else if (Event.EventName == TEXT("RespawnLiving"))
    {
        RestoreProps();
    }
    else if (Event.EventName == TEXT("DeathSettled"))
    {
        PropState = TEXT("released");
    }
}

void AMorphCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    Super::SetupPlayerInputComponent(PlayerInputComponent);
    PlayerInputComponent->BindAxis("MoveForward", this, &AMorphCharacter::MoveForward);
    PlayerInputComponent->BindAxis("MoveRight", this, &AMorphCharacter::MoveRight);
    PlayerInputComponent->BindAxis("LookUp", this, &AMorphCharacter::LookUp);
    PlayerInputComponent->BindAxis("LookYaw", this, &AMorphCharacter::LookYaw);
    PlayerInputComponent->BindAction("Jump", IE_Pressed, this, &AMorphCharacter::RequestJump);
    PlayerInputComponent->BindAction("Sprint", IE_Pressed, this, &AMorphCharacter::SprintPressed);
    PlayerInputComponent->BindAction("Sprint", IE_Released, this, &AMorphCharacter::SprintReleased);
    PlayerInputComponent->BindAction("Dash", IE_Pressed, this, &AMorphCharacter::DashForward);
    PlayerInputComponent->BindAction("Blink", IE_Pressed, this, &AMorphCharacter::RequestBlink);
    PlayerInputComponent->BindAction("Fire", IE_Pressed, this, &AMorphCharacter::FireSingle);
    PlayerInputComponent->BindAction("Burst", IE_Pressed, this, &AMorphCharacter::FireBurst);
    PlayerInputComponent->BindAction("Melee", IE_Pressed, this, &AMorphCharacter::MeleePrimary);
    PlayerInputComponent->BindAction("Channel", IE_Pressed, this, &AMorphCharacter::StartChannel);
    PlayerInputComponent->BindAction("Channel", IE_Released, this, &AMorphCharacter::FinishChannel);
    PlayerInputComponent->BindAction("Interrupt", IE_Pressed, this, &AMorphCharacter::InterruptChannel);
    PlayerInputComponent->BindAction("Charge", IE_Pressed, this, &AMorphCharacter::StartCharge);
    PlayerInputComponent->BindAction("Charge", IE_Released, this, &AMorphCharacter::ReleaseCharge);
    PlayerInputComponent->BindAction("CancelCharge", IE_Pressed, this, &AMorphCharacter::CancelCharge);
    PlayerInputComponent->BindAction("Camera", IE_Pressed, this, &AMorphCharacter::CycleCamera);
    PlayerInputComponent->BindAction("Dialogue", IE_Pressed, this, &AMorphCharacter::PlayDialogue);
    PlayerInputComponent->BindAction("Respawn", IE_Pressed, this, &AMorphCharacter::Respawn);
    PlayerInputComponent->BindAction("Reset", IE_Pressed, this, &AMorphCharacter::ResetShowcase);
    PlayerInputComponent->BindAction("Guide", IE_Pressed, this, &AMorphCharacter::ToggleGuide);
    PlayerInputComponent->BindAction("TurnLeft", IE_Pressed, this, &AMorphCharacter::TurnLeft90);
    PlayerInputComponent->BindAction("TurnRight", IE_Pressed, this, &AMorphCharacter::TurnRight90);
    PlayerInputComponent->BindAction("Team", IE_Pressed, this, &AMorphCharacter::ToggleTeam);
}

void AMorphCharacter::MoveForward(const float Value)
{
    KeyboardForward = Value;
    if (Value != 0.0f) bAnalogDrive = false;
}

void AMorphCharacter::MoveRight(const float Value)
{
    KeyboardRight = Value;
    if (Value != 0.0f) bAnalogDrive = false;
}

void AMorphCharacter::LookUp(const float Value)
{
    CameraOrbitPitch = FMath::Clamp(CameraOrbitPitch + Value * .08f, -1.0f, 1.0f);
}

void AMorphCharacter::LookYaw(const float Value)
{
    CameraOrbitYaw += Value * 1.5f;
}

void AMorphCharacter::SprintPressed()
{
    bSprinting = true;
}

void AMorphCharacter::SprintReleased()
{
    bSprinting = false;
}

void AMorphCharacter::DashForward()
{
    RequestDash();
}

void AMorphCharacter::FireSingle()
{
    RequestRanged(false);
}

void AMorphCharacter::FireBurst()
{
    RequestRanged(true);
}

void AMorphCharacter::MeleePrimary()
{
    RequestMelee(1);
}

void AMorphCharacter::TurnLeft90()
{
    RequestTurn(-90.0f);
}

void AMorphCharacter::TurnRight90()
{
    RequestTurn(90.0f);
}

void AMorphCharacter::ToggleTeam()
{
    SetTeam(1 - Team);
}

void AMorphCharacter::ToggleGuide()
{
    if (AMorphGameMode* Mode = GetWorld()->GetAuthGameMode<AMorphGameMode>()) Mode->ToggleControlPanel();
}
