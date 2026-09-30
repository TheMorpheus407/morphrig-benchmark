#include "OperativeCharacter.h"
#include "OperativeActionComponent.h"
#include "OperativeFaceComponent.h"
#include "OperativeAnimInstance.h"
#include "OperativeLibrary.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/AudioComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundBase.h"
#include "GameFramework/PlayerController.h"
#include "DrawDebugHelpers.h"
#include "Engine/OverlapResult.h"

// ================================================================================================ movement component

UOperativeMovementComponent::UOperativeMovementComponent()
{
	MaxStepHeight = OperativeConst::StepHeight;
	SetWalkableFloorAngle(32.f);
	GroundFriction = 9.f;
	bUseSeparateBrakingFriction = true;
	BrakingFriction = 0.f;
	BrakingFrictionFactor = 1.f;
	BrakingDecelerationWalking = 800.f;
	MaxAcceleration = 1100.f;
	MaxWalkSpeed = OperativeConst::SprintSpeed;
	GravityScale = 1.8f;
	JumpZVelocity = 620.f;
	AirControl = 0.35f;
	bOrientRotationToMovement = false;
	bUseControllerDesiredRotation = false;
	bCanWalkOffLedges = true;
	bRunPhysicsWithNoController = true;
	PerchRadiusThreshold = 0.f;
	bAlwaysCheckFloor = true;
}

AOperativeCharacter* UOperativeMovementComponent::GetOperative() const
{
	return Cast<AOperativeCharacter>(CharacterOwner);
}

void UOperativeMovementComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	if (AOperativeCharacter* Op = GetOperative())
	{
		Op->PreMovementTick(DeltaTime);
	}
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
}

float UOperativeMovementComponent::GetMaxSpeed() const
{
	if (MovementMode == MOVE_Walking || MovementMode == MOVE_NavWalking || MovementMode == MOVE_Falling)
	{
		return FMath::Max(GaitSpeed * MoveScale, 0.f);
	}
	return Super::GetMaxSpeed();
}

FVector UOperativeMovementComponent::ScaleInputAcceleration(const FVector& InputAcceleration) const
{
	return Super::ScaleInputAcceleration(InputAcceleration) * (MoveScale > 0.001f ? 1.f : 0.f);
}

float UOperativeMovementComponent::GetMaxBrakingDeceleration() const
{
	if (MovementMode == MOVE_Walking && bBrakeHard) return 1500.f;
	return Super::GetMaxBrakingDeceleration();
}

void UOperativeMovementComponent::OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode)
{
	Super::OnMovementModeChanged(PreviousMovementMode, PreviousCustomMode);
}

void UOperativeMovementComponent::PhysCustom(float DeltaTime, int32 Iterations)
{
	if (DeltaTime < MIN_TICK_TIME) return;
	AOperativeCharacter* Op = GetOperative();
	if (!Op || !Op->Actions) { SetMovementMode(MOVE_Walking); return; }
	const UOperativeActionComponent::FHostOutput& O = Op->Actions->GetHostOutput();
	FVector Delta = CustomMovementMode == CustomDash ? O.RootMotionWorldDelta : O.KnockbackVelocity * DeltaTime;
	Delta.Z = 0.f;
	Velocity = Delta / DeltaTime;
	Acceleration = FVector::ZeroVector;
	FStepDownResult StepDown;
	// a mode change clears the floor and MoveAlongFloor does nothing without one: find it first, otherwise the first frame of a dash or knockback is lost
	if (!CurrentFloor.IsWalkableFloor()) FindFloor(UpdatedComponent->GetComponentLocation(), CurrentFloor, false, nullptr);
	MoveAlongFloor(Velocity, DeltaTime, &StepDown);
	if (StepDown.bComputedFloor) CurrentFloor = StepDown.FloorResult;
	else FindFloor(UpdatedComponent->GetComponentLocation(), CurrentFloor, Velocity.IsZero(), nullptr);
	if (!CurrentFloor.IsWalkableFloor())
	{
		SetMovementMode(MOVE_Falling);
		return;
	}
	AdjustFloorHeight();
	SetBaseFromFloor(CurrentFloor);
}

// ================================================================================================ character

AOperativeCharacter::AOperativeCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UOperativeMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;
	AutoPossessAI = EAutoPossessAI::Disabled;

	GetCapsuleComponent()->InitCapsuleSize(OperativeConst::CapsuleRadius, OperativeConst::CapsuleHalfHeight);
	GetCapsuleComponent()->SetCollisionProfileName(TEXT("Pawn"));

	USkeletalMeshComponent* M = GetMesh();
	M->SetRelativeLocation(FVector(0.f, 0.f, -OperativeConst::CapsuleHalfHeight));
	M->SetRelativeRotation(FRotator::ZeroRotator);
	M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
	M->SetAnimInstanceClass(UOperativeAnimInstance::StaticClass());
	M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	M->bEnableUpdateRateOptimizations = false;
	M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	M->SetCastShadow(true);
	M->bSelfShadowOnly = false;

	Actions = CreateDefaultSubobject<UOperativeActionComponent>(TEXT("Actions"));
	Face = CreateDefaultSubobject<UOperativeFaceComponent>(TEXT("Face"));

	PowerCellComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PowerCell"));
	PowerCellComp->SetupAttachment(M);
	PowerCellComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PowerCellComp->SetCastShadow(true);
	BeaconComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BeaconAttached"));
	BeaconComp->SetupAttachment(M);
	BeaconComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BeaconComp->SetCastShadow(true);
	VoiceComp = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	VoiceComp->SetupAttachment(M);
	VoiceComp->bAutoActivate = false;
	VoiceComp->bIsUISound = true;

	GetCharacterMovement()->NavAgentProps.bCanCrouch = false;
}

void AOperativeCharacter::PostInitializeComponents()
{
	Super::PostInitializeComponents();
	SpawnLocation = GetActorLocation();
	SpawnYaw = GetActorRotation().Yaw;
}

UOperativeAnimInstance* AOperativeCharacter::GetOperativeAnim() const
{
	return Cast<UOperativeAnimInstance>(GetMesh()->GetAnimInstance());
}

void AOperativeCharacter::ApplyAssets()
{
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	if (!Lib || !Lib->GetAssets()) return;
	UOperativeAssets* A = Lib->GetAssets();
	if (A->Mesh && GetMesh()->GetSkeletalMeshAsset() != A->Mesh)
	{
		GetMesh()->SetSkeletalMesh(A->Mesh);
		GetMesh()->SetAnimInstanceClass(UOperativeAnimInstance::StaticClass());
	}
	// props and voice attach to sockets once the skeletal mesh (and with it the sockets) exists
	{
		const FAttachmentTransformRules Rules(EAttachmentRule::SnapToTarget, EAttachmentRule::SnapToTarget, EAttachmentRule::KeepRelative, false);
		PowerCellComp->AttachToComponent(GetMesh(), Rules, FName("prop_cell"));
		BeaconComp->AttachToComponent(GetMesh(), Rules, FName("prop_beacon"));
		VoiceComp->AttachToComponent(GetMesh(), Rules, FName("fx_mouth"));
	}
	if (A->PowerCellMesh) PowerCellComp->SetStaticMesh(A->PowerCellMesh);
	if (A->BeaconMesh) BeaconComp->SetStaticMesh(A->BeaconMesh);
	if (A->DialogueSound) VoiceComp->SetSound(A->DialogueSound);
	if (const TObjectPtr<UMaterialInterface>* Fx = A->ExtraMaterials.Find(FName("Fx"))) FxBase = *Fx;
	bAssetsApplied = true;
	ApplyTeamMaterials();
	SetForcedLOD(ForcedLOD);
}

void AOperativeCharacter::ApplyTeamMaterials()
{
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	if (!Lib || !Lib->GetAssets()) return;
	const UOperativeAssets* A = Lib->GetAssets();
	const TArray<TObjectPtr<UMaterialInterface>>& Mats = Team == EOperativeTeam::A ? A->TeamAMaterials : A->TeamBMaterials;
	if (RenderMode == 0)
	{
		for (int32 I = 0; I < A->MaterialSlotNames.Num() && I < Mats.Num(); ++I)
		{
			if (!Mats[I]) continue;
			const int32 Slot = GetMesh()->GetMaterialIndex(A->MaterialSlotNames[I]);
			if (Slot != INDEX_NONE) GetMesh()->SetMaterial(Slot, Mats[I]);
			// props use the same slot names (MI_armor, MI_cyber)
			for (UStaticMeshComponent* P : { PowerCellComp.Get(), BeaconComp.Get() })
			{
				if (!P) continue;
				const int32 PS = P->GetMaterialIndex(A->MaterialSlotNames[I]);
				if (PS != INDEX_NONE) P->SetMaterial(PS, Mats[I]);
			}
		}
	}
	ApplyRenderMaterials();
}

void AOperativeCharacter::ApplyRenderMaterials()
{
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	if (!Lib || !Lib->GetAssets()) return;
	const UOperativeAssets* A = Lib->GetAssets();
	UMaterialInterface* Override = nullptr;
	switch (RenderMode)
	{
	case 1: if (const TObjectPtr<UMaterialInterface>* M = A->ExtraMaterials.Find(FName("Normal"))) Override = *M; break;
	case 2: if (const TObjectPtr<UMaterialInterface>* M = A->ExtraMaterials.Find(FName("Wireframe"))) Override = *M; break;
	case 3: if (const TObjectPtr<UMaterialInterface>* M = A->ExtraMaterials.Find(FName("Clay"))) Override = *M; break;
	default: break;
	}
	if (Override)
	{
		for (int32 S = 0; S < GetMesh()->GetNumMaterials(); ++S) GetMesh()->SetMaterial(S, Override);
		for (UStaticMeshComponent* P : { PowerCellComp.Get(), BeaconComp.Get() })
		{
			if (!P) continue;
			for (int32 S = 0; S < P->GetNumMaterials(); ++S) P->SetMaterial(S, Override);
		}
	}
	UMaterialInterface* Outline = nullptr;
	const int32 TeamIndex = Team == EOperativeTeam::A ? 0 : 1;
	if (bOutline && !bOutlineSuppressed && RenderMode == 0 && A->OutlineMaterials.IsValidIndex(TeamIndex)) Outline = A->OutlineMaterials[TeamIndex];
	GetMesh()->SetOverlayMaterial(Outline);
}

void AOperativeCharacter::SetTeam(EOperativeTeam NewTeam)
{
	Team = NewTeam;
	ApplyTeamMaterials();
}

void AOperativeCharacter::SetOutlineEnabled(bool bEnabled)
{
	bOutline = bEnabled;
	ApplyRenderMaterials();
}

void AOperativeCharacter::SetOutlineSuppressed(bool bSuppressed)
{
	if (bOutlineSuppressed == bSuppressed) return;
	bOutlineSuppressed = bSuppressed;
	ApplyRenderMaterials();
}

void AOperativeCharacter::SetRenderMode(int32 Mode)
{
	RenderMode = FMath::Clamp(Mode, 0, 3);
	ApplyTeamMaterials();
}

void AOperativeCharacter::SetForcedLOD(int32 Lod)
{
	ForcedLOD = FMath::Clamp(Lod, 0, 3);
	GetMesh()->SetForcedLOD(ForcedLOD);
}

void AOperativeCharacter::BeginPlay()
{
	Super::BeginPlay();
	SpawnLocation = GetActorLocation();
	SpawnYaw = GetActorRotation().Yaw;
	LastLocation = SpawnLocation;
	ApplyAssets();
	if (Actions) Actions->OnEvent.AddUObject(this, &AOperativeCharacter::OnOperativeEvent);
}

void AOperativeCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	ResetFx();
	if (WorldBeacon.IsValid()) WorldBeacon->Destroy();
	Super::EndPlay(EndPlayReason);
}

void AOperativeCharacter::SetMoveIntent(FVector WorldDirection, float SpeedCmS)
{
	WorldDirection.Z = 0.f;
	DesiredMoveDir = WorldDirection.GetSafeNormal();
	DesiredMoveSpeed = DesiredMoveDir.IsNearlyZero() ? 0.f : FMath::Clamp(SpeedCmS, 0.f, OperativeConst::SprintSpeed);
}

void AOperativeCharacter::SetAimPoint(FVector WorldPoint)
{
	LastAimPoint = WorldPoint;
	if (Actions) Actions->SetAimTarget(WorldPoint, true);
}

void AOperativeCharacter::SetAimHold(bool bHold)
{
	if (Actions) Actions->SetAimHold(bHold);
}

void AOperativeCharacter::SetFacingYaw(float Yaw)
{
	SetActorRotation(FRotator(0.f, Yaw, 0.f));
}

// ------------------------------------------------------------------------------------------------ per frame

bool AOperativeCharacter::GetSocketTransformSafe(FName Socket, FTransform& Out) const
{
	const USkeletalMeshComponent* M = GetMesh();
	if (!M || !M->GetSkeletalMeshAsset() || !M->DoesSocketExist(Socket)) return false;
	Out = M->GetSocketTransform(Socket);
	return true;
}

bool AOperativeCharacter::IsGroundedForActions() const
{
	const UCharacterMovementComponent* MC = GetCharacterMovement();
	if (!MC) return false;
	if (MC->IsMovingOnGround()) return true;
	return MC->MovementMode == MOVE_Custom && MC->CurrentFloor.IsWalkableFloor();
}

FVector AOperativeCharacter::GetAimOrigin() const
{
	FTransform T;
	if (GetSocketTransformSafe(FName("fx_chest"), T)) return T.GetLocation();
	return GetActorLocation() + FVector(0.f, 0.f, 45.f);
}

FVector AOperativeCharacter::GetMuzzleLocation() const
{
	FTransform T;
	if (GetSocketTransformSafe(FName("emitter_muzzle"), T)) return T.GetLocation();
	return GetAimOrigin() + GetActorForwardVector() * 40.f;
}

FVector AOperativeCharacter::GetMuzzleDirection() const
{
	FTransform T;
	if (GetSocketTransformSafe(FName("emitter_muzzle"), T)) return T.GetUnitAxis(EAxis::X);
	return GetActorForwardVector();
}

FVector AOperativeCharacter::GetWorldBeaconLocation() const
{
	return WorldBeacon.IsValid() ? WorldBeacon->GetActorLocation() : FVector::ZeroVector;
}

void AOperativeCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bAutopilot) TickAutopilot(DeltaSeconds);
	const FVector Loc = GetActorLocation();
	TravelSinceReset += FVector::Dist2D(Loc, LastLocation);
	LastLocation = Loc;
	UpdateMeleeSweep(DeltaSeconds);
	UpdateFx(DeltaSeconds);
	if (UOperativeAnimInstance* AI = GetOperativeAnim())
	{
		if (Actions) AI->SetRecipe(Actions->GetRecipe());
	}
}

void AOperativeCharacter::PreMovementTick(float Dt)
{
	if (!Actions) return;
	UOperativeMovementComponent* MC = Cast<UOperativeMovementComponent>(GetCharacterMovement());
	if (!MC) return;
	if (!bAssetsApplied) ApplyAssets();

	Actions->SetMoveInput(DesiredMoveDir, DesiredMoveSpeed);
	MC->GaitSpeed = FMath::Max(DesiredMoveSpeed, 50.f);
	UpdateFootIK(Dt);
	Actions->UpdateActions(Dt);
	// the mesh ticks after the movement component: hand the recipe over now so the pose shows this frame's state (no one frame latency)
	if (UOperativeAnimInstance* AI = GetOperativeAnim()) AI->SetRecipe(Actions->GetRecipe());
	const UOperativeActionComponent::FHostOutput& O = Actions->GetHostOutput();

	// facing
	UpdateFacing(Dt);

	// movement policy
	MC->MoveScale = O.MoveSpeedScale;
	MC->bBrakeHard = O.bBrakeToStop;
	MC->AirControl = O.bAirControl ? 0.35f : 0.f;
	const bool bWantsMove = !DesiredMoveDir.IsNearlyZero() && DesiredMoveSpeed > 5.f && O.MoveSpeedScale > 0.001f && !Actions->IsRooted();
	if (bWantsMove) AddMovementInput(DesiredMoveDir, 1.f);

	// custom modes for dash root motion and knockback
	const bool bOnGround = MC->IsMovingOnGround() || (MC->MovementMode == MOVE_Custom && MC->CurrentFloor.IsWalkableFloor());
	if (O.bDashActive && bOnGround)
	{
		if (MC->MovementMode != MOVE_Custom || MC->CustomMovementMode != UOperativeMovementComponent::CustomDash) MC->SetMovementMode(MOVE_Custom, UOperativeMovementComponent::CustomDash);
	}
	else if (O.bKnockbackActive && bOnGround)
	{
		if (MC->MovementMode != MOVE_Custom || MC->CustomMovementMode != UOperativeMovementComponent::CustomKnockback) MC->SetMovementMode(MOVE_Custom, UOperativeMovementComponent::CustomKnockback);
	}
	else if (MC->MovementMode == MOVE_Custom)
	{
		MC->Velocity = FVector::ZeroVector;
		MC->SetMovementMode(MC->CurrentFloor.IsWalkableFloor() ? MOVE_Walking : MOVE_Falling);
	}
	UpdateMeshSmoothing(Dt);
}

void AOperativeCharacter::UpdateFacing(float Dt)
{
	const UOperativeActionComponent::FHostOutput& O = Actions->GetHostOutput();
	const float Yaw = GetActorRotation().Yaw;
	float NewYaw = Yaw;
	if (O.bFacingDriven) NewYaw = O.DrivenYaw;
	else if (O.TurnRateDegS > 0.f) NewYaw = FMath::FixedTurn(Yaw, O.DesiredYaw, O.TurnRateDegS * Dt);
	if (!FMath::IsNearlyEqual(NewYaw, Yaw, 0.001f)) SetActorRotation(FRotator(0.f, NewYaw, 0.f));
}

void AOperativeCharacter::UpdateMeshSmoothing(float Dt)
{
	const float CapZ = GetActorLocation().Z;
	const UCharacterMovementComponent* MC = GetCharacterMovement();
	if (bHaveCapsuleZ && MC->IsMovingOnGround())
	{
		const float Expected = MC->Velocity.Z * Dt;
		const float Jump = (CapZ - LastCapsuleZ) - Expected;
		if (FMath::Abs(Jump) > 1.2f && FMath::Abs(Jump) < 40.f)
		{
			MeshZSmoothOffset = FMath::Clamp(MeshZSmoothOffset - Jump, -30.f, 30.f);
		}
	}
	LastCapsuleZ = CapZ;
	bHaveCapsuleZ = true;
	MeshZSmoothOffset = FMath::FInterpTo(MeshZSmoothOffset, 0.f, Dt, MC->IsMovingOnGround() ? 9.f : 20.f);
	if (FMath::Abs(MeshZSmoothOffset) < 0.01f) MeshZSmoothOffset = 0.f;
	GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -OperativeConst::CapsuleHalfHeight + MeshZSmoothOffset));
}

void AOperativeCharacter::UpdateFootIK(float Dt)
{
	if (!Actions) return;
	USkeletalMeshComponent* M = GetMesh();
	const bool bReady = M && M->GetSkeletalMeshAsset() && M->DoesSocketExist(FName("foot_l"));
	FOperativeFootIK Feet[2];
	if (!bReady)
	{
		Actions->SetFootIK(false, 0.f, Feet[0], Feet[1]);
		return;
	}
	const FVector MeshOrigin = M->GetComponentLocation();
	const FTransform ActorT = GetActorTransform();
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeFootIK), false, this);
	float Target[2] = {0.f, 0.f};
	const FName Bones[2] = { FName("foot_l"), FName("foot_r") };
	for (int32 S = 0; S < 2; ++S)
	{
		const FVector Foot = M->GetSocketLocation(Bones[S]);
		const FVector Start(Foot.X, Foot.Y, MeshOrigin.Z + 55.f);
		const FVector End(Foot.X, Foot.Y, MeshOrigin.Z - 45.f);
		FHitResult Hit;
		FVector Normal = FVector::UpVector;
		float Offset = 0.f;
		if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params) && Hit.bBlockingHit)
		{
			Normal = Hit.ImpactNormal.GetSafeNormal();
			Offset = Hit.ImpactPoint.Z - MeshOrigin.Z;
		}
		Target[S] = FMath::Clamp(Offset, -FootIKMaxOffset, FootIKMaxOffset);
		FootOffsetSmoothed[S] = FMath::FInterpTo(FootOffsetSmoothed[S], Target[S], Dt, 22.f);
		FootNormalSmoothed[S] = FMath::VInterpTo(FootNormalSmoothed[S], Normal, Dt, 14.f).GetSafeNormal();
		Feet[S].bValid = true;
		Feet[S].GroundOffset = FootOffsetSmoothed[S];
		Feet[S].Normal = ActorT.InverseTransformVectorNoScale(FootNormalSmoothed[S]);
	}
	const float PelvisTarget = FMath::Clamp(FMath::Min(0.f, FMath::Min(Target[0], Target[1])), -FootIKMaxOffset, 0.f);
	PelvisOffsetSmoothed = FMath::FInterpTo(PelvisOffsetSmoothed, PelvisTarget, Dt, 12.f);
	Actions->SetFootIK(true, PelvisOffsetSmoothed, Feet[0], Feet[1]);
}

// ------------------------------------------------------------------------------------------------ reset

void AOperativeCharacter::ResetOperative(bool bMoveToSpawn)
{
	ResetFx();
	HostResetProps();
	if (bMoveToSpawn)
	{
		TeleportTo(SpawnLocation, FRotator(0.f, SpawnYaw, 0.f), false, true);
	}
	GetCharacterMovement()->Velocity = FVector::ZeroVector;
	GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	DesiredMoveDir = FVector::ZeroVector;
	DesiredMoveSpeed = 0.f;
	FootOffsetSmoothed[0] = FootOffsetSmoothed[1] = 0.f;
	PelvisOffsetSmoothed = 0.f;
	MeshZSmoothOffset = 0.f;
	TravelSinceReset = 0.f;
	ShotsFired = 0;
	BladeHitsTotal = 0;
	LastLocation = GetActorLocation();
	if (Actions) Actions->ResetAll();
}

// ------------------------------------------------------------------------------------------------ host API

void AOperativeCharacter::HostJump()
{
	LaunchCharacter(FVector(0.f, 0.f, JumpVelocity), false, true);
}

void AOperativeCharacter::HostLaunch(const FVector& Velocity)
{
	LaunchCharacter(Velocity, true, true);
}

void AOperativeCharacter::HostSetMeshVisible(bool bVisible)
{
	bMeshVisible = bVisible;
	GetMesh()->SetVisibility(bVisible, false);
	PowerCellComp->SetVisibility(bVisible, false);
	BeaconComp->SetVisibility(bVisible && bBeaconAttachedVisible, false);
}

void AOperativeCharacter::HostBlinkTeleport(const FVector& Dir, float Distance)
{
	const FVector From = GetActorLocation();
	const float HalfH = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const float Radius = GetCapsuleComponent()->GetScaledCapsuleRadius();
	FVector To = From + Dir.GetSafeNormal2D() * Distance;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeBlink), false, this);
	FHitResult Hit;
	if (GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(Radius, HalfH - 8.f), Params) && Hit.bBlockingHit)
	{
		To = From + (To - From) * FMath::Max(Hit.Time - 0.02f, 0.f);
	}
	// find the floor below the destination
	FHitResult Floor;
	const FVector TraceStart = To + FVector(0.f, 0.f, 120.f);
	const FVector TraceEnd = To - FVector(0.f, 0.f, 400.f);
	if (GetWorld()->LineTraceSingleByChannel(Floor, TraceStart, TraceEnd, ECC_Visibility, Params) && Floor.bBlockingHit)
	{
		To.Z = Floor.ImpactPoint.Z + HalfH + 1.f;
	}
	else
	{
		To = From;
	}
	PulseFx(From + FVector(0.f, 0.f, 90.f), FLinearColor(0.4f, 0.8f, 1.f), 90.f, 0.35f);
	HostSetMeshVisible(false);
	TeleportTo(To, GetActorRotation(), false, true);
	GetCharacterMovement()->Velocity = FVector::ZeroVector;
	MeshZSmoothOffset = 0.f;
	bHaveCapsuleZ = false;
	if (Actions) Actions->SetTeleportedThisFrame();
	PulseFx(To + FVector(0.f, 0.f, 90.f), FLinearColor(0.4f, 0.8f, 1.f), 90.f, 0.35f);
}

void AOperativeCharacter::HostSpawnBeacon()
{
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	if (!Lib || !Lib->GetAssets() || !Lib->GetAssets()->BeaconMesh) return;
	FTransform T;
	if (!GetSocketTransformSafe(FName("prop_beacon"), T)) T = FTransform(GetActorLocation());
	HostRecallBeacon();
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* B = GetWorld()->SpawnActor<AStaticMeshActor>(T.GetLocation(), T.Rotator(), SP);
	if (!B) return;
	B->SetMobility(EComponentMobility::Movable);
	B->GetStaticMeshComponent()->SetStaticMesh(Lib->GetAssets()->BeaconMesh);
	B->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	B->GetStaticMeshComponent()->SetWorldScale3D(BeaconComp->GetComponentScale());
	const TArray<TObjectPtr<UMaterialInterface>>& Mats = Team == EOperativeTeam::A ? Lib->GetAssets()->TeamAMaterials : Lib->GetAssets()->TeamBMaterials;
	for (int32 I = 0; I < Lib->GetAssets()->MaterialSlotNames.Num() && I < Mats.Num(); ++I)
	{
		const int32 S = B->GetStaticMeshComponent()->GetMaterialIndex(Lib->GetAssets()->MaterialSlotNames[I]);
		if (S != INDEX_NONE && Mats[I]) B->GetStaticMeshComponent()->SetMaterial(S, Mats[I]);
	}
	WorldBeacon = B;
	bBeaconAttachedVisible = false;
	BeaconComp->SetVisibility(false, false);
	BeaconSettleTimer = 0.f;
	BeaconSpawnTransform = T;
}

void AOperativeCharacter::HostRecallBeacon()
{
	if (WorldBeacon.IsValid())
	{
		WorldBeacon->Destroy();
		WorldBeacon.Reset();
	}
	bBeaconAttachedVisible = true;
	BeaconComp->SetVisibility(bMeshVisible, false);
}

void AOperativeCharacter::HostPlayDialogue()
{
	if (VoiceComp && VoiceComp->Sound)
	{
		VoiceComp->Stop();
		VoiceComp->Play(0.f);
		DialogueAudioStartTime = GetWorld()->GetTimeSeconds();
		UE_LOG(LogMorphRig, Log, TEXT("Operative: dialogue audio started (%s)"), *VoiceComp->Sound->GetName());
	}
}

void AOperativeCharacter::HostStopDialogue()
{
	if (VoiceComp && VoiceComp->IsPlaying()) VoiceComp->Stop();
}

void AOperativeCharacter::HostOnDeath()
{
	HostStopDialogue();
	ResetFx();
	GetCharacterMovement()->Velocity = FVector::ZeroVector;
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
}

void AOperativeCharacter::HostOnRespawn()
{
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
	HostSetMeshVisible(true);
}

void AOperativeCharacter::HostResetProps()
{
	if (WorldBeacon.IsValid())
	{
		WorldBeacon->Destroy();
		WorldBeacon.Reset();
	}
	bBeaconAttachedVisible = true;
	BeaconComp->SetVisibility(true, false);
	PowerCellComp->SetVisibility(true, false);
	GetMesh()->SetVisibility(true, false);
	bMeshVisible = true;
	HostStopDialogue();
	ResetFx();
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
}

// ------------------------------------------------------------------------------------------------ event hooks

void AOperativeCharacter::HandleMuzzleFire(int32 Index)
{
	const FVector Muzzle = GetMuzzleLocation();
	FVector Dir = GetMuzzleDirection();
	if (Actions)
	{
		// the hit ray follows the aim point; the tracer starts at the animated muzzle
		FVector Aim = LastAimPoint;
		if (!Aim.IsNearlyZero())
		{
			FVector To = (Aim - GetAimOrigin());
			if (!To.IsNearlyZero()) Dir = To.GetSafeNormal();
		}
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeShot), false, this);
	FHitResult Hit;
	const FVector Origin = GetAimOrigin();
	const FVector End = Origin + Dir * 6000.f;
	FVector HitLoc = End;
	AActor* HitActor = nullptr;
	if (GetWorld()->LineTraceSingleByChannel(Hit, Origin, End, ECC_Visibility, Params) && Hit.bBlockingHit)
	{
		HitLoc = Hit.ImpactPoint;
		HitActor = Hit.GetActor();
	}
	++ShotsFired;
	SpawnTracer(Muzzle, HitLoc, Team == EOperativeTeam::A ? FLinearColor(0.1f, 0.9f, 1.f) : FLinearColor(1.f, 0.15f, 0.65f), 0.09f, 1.6f);
	PulseFx(Muzzle, FLinearColor(1.f, 0.9f, 0.6f), 14.f, 0.08f);
	OnMuzzleHit.Broadcast(HitLoc, HitActor);
}

void AOperativeCharacter::OnOperativeEvent(const FOperativeEventInfo& Info)
{
	const FName N = Info.Name;
	const FLinearColor Accent = Team == EOperativeTeam::A ? FLinearColor(0.1f, 0.9f, 1.f) : FLinearColor(1.f, 0.15f, 0.65f);
	if (N == FName("muzzle_fire"))
	{
		int32 Index = 0;
		const int32 Eq = Info.Params.Find(TEXT("="));
		if (Eq != INDEX_NONE) Index = FCString::Atoi(*Info.Params.Mid(Eq + 1));
		HandleMuzzleFire(Index);
	}
	else if (N == FName("cast_release"))
	{
		const FName Clip = Info.ClipId;
		if (Clip == FName("cast_self")) PulseFx(GetActorLocation(), Accent, 220.f, 0.5f);
		else if (Clip == FName("cast_ground"))
		{
			FVector P = LastAimPoint.IsNearlyZero() ? GetActorLocation() + GetActorForwardVector() * 300.f : LastAimPoint;
			PulseFx(P, Accent, 200.f, 0.7f);
			SpawnTracer(GetMuzzleLocation(), P, Accent, 0.15f, 2.f);
		}
		else
		{
			FVector P = GetMuzzleLocation() + GetMuzzleDirection() * 900.f;
			if (!LastAimPoint.IsNearlyZero()) P = GetMuzzleLocation() + (LastAimPoint - GetAimOrigin()).GetSafeNormal() * 900.f;
			SpawnTracer(GetMuzzleLocation(), P, Accent, 0.22f, 8.f);
			PulseFx(GetMuzzleLocation(), Accent, 30.f, 0.15f);
		}
	}
	else if (N == FName("channel_sustain_begin")) { bBeamOn = true; }
	else if (N == FName("channel_release") || N == FName("channel_interrupted")) { bBeamOn = false; }
	else if (N == FName("charge_release"))
	{
		const float Frac = Actions ? FMath::Max(Actions->GetChargeFraction(), 0.15f) : 0.5f;
		FVector P = GetMuzzleLocation() + GetMuzzleDirection() * 1600.f;
		if (!LastAimPoint.IsNearlyZero()) P = GetMuzzleLocation() + (LastAimPoint - GetAimOrigin()).GetSafeNormal() * 1600.f;
		SpawnTracer(GetMuzzleLocation(), P, Accent, 0.3f, 4.f + 16.f * Frac);
		PulseFx(GetMuzzleLocation(), Accent, 40.f + 60.f * Frac, 0.25f);
	}
	else if (N == FName("uplink_sustain_begin")) { bRingOn = true; }
	else if (N == FName("uplink_complete") || N == FName("uplink_cancelled")) { bRingOn = false; PulseFx(GetActorLocation(), Accent, 160.f, 0.5f); }
	else if (N == FName("ground_impact") || N == FName("land_impact_heavy")) { PulseFx(GetActorLocation() - FVector(0.f, 0.f, 88.f), FLinearColor(0.8f, 0.8f, 0.8f), 70.f, 0.3f); }
	else if (N == FName("hit_peak")) { PulseFx(GetAimOrigin(), FLinearColor(1.f, 0.4f, 0.2f), 30.f, 0.15f); }
	else if (N == FName("respawn_activate")) { PulseFx(GetActorLocation(), Accent, 200.f, 0.6f); }
	else if (N == FName("deploy_settle")) { PulseFx(GetWorldBeaconLocation(), Accent, 50.f, 0.3f); }
}

// ------------------------------------------------------------------------------------------------ melee sweep

void AOperativeCharacter::UpdateMeleeSweep(float Dt)
{
	if (!Actions) return;
	const int32 Serial = Actions->GetMeleeWindowSerial();
	if (Serial != LastMeleeWindowSerial)
	{
		LastMeleeWindowSerial = Serial;
		BladeHitThisWindow.Empty();
		bHaveBlade = false;
	}
	if (!Actions->IsMeleeWindowOpen())
	{
		bHaveBlade = false;
		return;
	}
	FTransform Base, Tip;
	if (!GetSocketTransformSafe(FName("blade_base"), Base) || !GetSocketTransformSafe(FName("blade_tip"), Tip)) return;
	const FVector B = Base.GetLocation();
	const FVector Dir = (Tip.GetLocation() - B).GetSafeNormal();
	const float Len = FMath::Max((Tip.GetLocation() - B).Size(), 25.f) + 30.f;   // extended blade
	const FVector T = B + Dir * Len;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeBlade), false, this);
	const FCollisionShape Shape = FCollisionShape::MakeSphere(14.f);
	for (int32 K = 0; K < 3; ++K)
	{
		const FVector P = FMath::Lerp(B, T, K / 2.f);
		const FVector PrevP = bHaveBlade ? FMath::Lerp(LastBladeBase, LastBladeTip, K / 2.f) : P;
		TArray<FHitResult> Hits;
		GetWorld()->SweepMultiByChannel(Hits, PrevP, P, FQuat::Identity, ECC_WorldDynamic, Shape, Params);
		TArray<FOverlapResult> Ov;
		GetWorld()->OverlapMultiByChannel(Ov, P, FQuat::Identity, ECC_WorldDynamic, Shape, Params);
		auto Report = [&](AActor* A, const FVector& Loc)
		{
			if (!A || BladeHitThisWindow.Contains(A)) return;
			BladeHitThisWindow.Add(A);
			++BladeHitsTotal;
			OnBladeHit.Broadcast(Loc, A);
			PulseFx(Loc, FLinearColor(1.f, 0.6f, 0.2f), 26.f, 0.14f);
		};
		for (const FHitResult& H : Hits) Report(H.GetActor(), H.ImpactPoint);
		for (const FOverlapResult& O : Ov) Report(O.GetActor(), P);
	}
	LastBladeBase = B;
	LastBladeTip = T;
	bHaveBlade = true;
}

// ------------------------------------------------------------------------------------------------ FX (effects made from engine basic shapes)

static UStaticMesh* LoadBasicShape(const TCHAR* Path)
{
	return LoadObject<UStaticMesh>(nullptr, Path);
}

void AOperativeCharacter::SpawnTracer(const FVector& From, const FVector& To, const FLinearColor& Color, float Life, float Thickness)
{
	UStaticMesh* Cyl = LoadBasicShape(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (!Cyl || !FxBase) return;
	FFxItem* Slot = nullptr;
	for (FFxItem& It : FxItems)
	{
		if (It.Life <= 0.f && It.Comp.IsValid() && It.bTracer) { Slot = &It; break; }
	}
	if (!Slot)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetStaticMesh(Cyl);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(GetRootComponent());
		C->RegisterComponent();
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(FxBase, this);
		C->SetMaterial(0, MID);
		FxMaterials.Add(MID);
		FFxItem It;
		It.Comp = C;
		It.bTracer = true;
		FxItems.Add(It);
		Slot = &FxItems.Last();
	}
	Slot->Life = Slot->MaxLife = Life;
	Slot->Start = From;
	Slot->End = To;
	Slot->Thickness = Thickness;
	Slot->Color = Color;
	Slot->bTracer = true;
	UStaticMeshComponent* C = Slot->Comp.Get();
	C->SetVisibility(true);
	C->SetStaticMesh(Cyl);
}

void AOperativeCharacter::PulseFx(const FVector& At, const FLinearColor& Color, float Radius, float Life)
{
	UStaticMesh* Sph = LoadBasicShape(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (!Sph || !FxBase) return;
	FFxItem* Slot = nullptr;
	for (FFxItem& It : FxItems)
	{
		if (It.Life <= 0.f && It.Comp.IsValid() && !It.bTracer) { Slot = &It; break; }
	}
	if (!Slot)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetStaticMesh(Sph);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(GetRootComponent());
		C->RegisterComponent();
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(FxBase, this);
		C->SetMaterial(0, MID);
		FxMaterials.Add(MID);
		FFxItem It;
		It.Comp = C;
		It.bTracer = false;
		FxItems.Add(It);
		Slot = &FxItems.Last();
	}
	Slot->Life = Slot->MaxLife = Life;
	Slot->Start = At;
	Slot->Radius = Radius;
	Slot->Color = Color;
	Slot->bTracer = false;
	Slot->Comp->SetVisibility(true);
}

void AOperativeCharacter::UpdateFx(float Dt)
{
	for (FFxItem& It : FxItems)
	{
		UStaticMeshComponent* C = It.Comp.Get();
		if (!C) continue;
		if (It.Life <= 0.f)
		{
			if (C->IsVisible()) C->SetVisibility(false);
			continue;
		}
		It.Life -= Dt;
		const float U = FMath::Clamp(1.f - It.Life / FMath::Max(It.MaxLife, 1e-3f), 0.f, 1.f);
		UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0));
		if (It.bTracer)
		{
			const FVector D = It.End - It.Start;
			const float L = D.Size();
			C->SetWorldLocationAndRotation((It.Start + It.End) * 0.5f, FRotationMatrix::MakeFromZ(D.GetSafeNormal()).Rotator());
			C->SetWorldScale3D(FVector(It.Thickness / 100.f, It.Thickness / 100.f, L / 100.f));
			if (MID) { MID->SetVectorParameterValue(TEXT("Color"), It.Color); MID->SetScalarParameterValue(TEXT("Opacity"), 1.f - U); }
		}
		else
		{
			C->SetWorldLocation(It.Start);
			C->SetWorldRotation(FRotator::ZeroRotator);
			const float R = It.Radius * (0.25f + 0.75f * U);
			C->SetWorldScale3D(FVector(R / 50.f));
			if (MID) { MID->SetVectorParameterValue(TEXT("Color"), It.Color); MID->SetScalarParameterValue(TEXT("Opacity"), (1.f - U) * 0.9f); }
		}
	}
	const FLinearColor Accent = Team == EOperativeTeam::A ? FLinearColor(0.1f, 0.9f, 1.f) : FLinearColor(1.f, 0.15f, 0.65f);
	auto Persistent = [&](TWeakObjectPtr<UStaticMeshComponent>& Ref, const TCHAR* Shape) -> UStaticMeshComponent*
	{
		if (Ref.IsValid()) return Ref.Get();
		UStaticMesh* SM = LoadBasicShape(Shape);
		if (!SM || !FxBase) return nullptr;
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
		C->SetStaticMesh(SM);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(GetRootComponent());
		C->RegisterComponent();
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(FxBase, this);
		C->SetMaterial(0, MID);
		FxMaterials.Add(MID);
		Ref = C;
		return C;
	};
	// channel beam
	if (bBeamOn && Actions && Actions->IsChannelSustained())
	{
		if (UStaticMeshComponent* C = Persistent(BeamComp, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
		{
			const FVector From = GetMuzzleLocation();
			FVector Dir = GetMuzzleDirection();
			if (!LastAimPoint.IsNearlyZero()) Dir = (LastAimPoint - GetAimOrigin()).GetSafeNormal();
			FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeBeam), false, this);
			FHitResult Hit;
			FVector End = From + Dir * 1800.f;
			if (GetWorld()->LineTraceSingleByChannel(Hit, From, End, ECC_Visibility, Params) && Hit.bBlockingHit) End = Hit.ImpactPoint;
			const float L = (End - From).Size();
			const float Pulse = 1.f + 0.15f * FMath::Sin(GetWorld()->GetTimeSeconds() * 30.f);
			C->SetVisibility(true);
			C->SetWorldLocationAndRotation((From + End) * 0.5f, FRotationMatrix::MakeFromZ(Dir).Rotator());
			C->SetWorldScale3D(FVector(0.06f * Pulse, 0.06f * Pulse, L / 100.f));
			if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0))) { MID->SetVectorParameterValue(TEXT("Color"), Accent); MID->SetScalarParameterValue(TEXT("Opacity"), 0.9f); }
		}
	}
	else if (BeamComp.IsValid())
	{
		BeamComp->SetVisibility(false);
		bBeamOn = false;
	}
	// charge orb
	if (Actions && Actions->IsChargeHolding())
	{
		if (UStaticMeshComponent* C = Persistent(OrbComp, TEXT("/Engine/BasicShapes/Sphere.Sphere")))
		{
			const float F = FMath::Max(Actions->GetChargeFraction(), 0.05f);
			C->SetVisibility(true);
			C->SetWorldLocation(GetMuzzleLocation() + GetMuzzleDirection() * 8.f);
			C->SetWorldScale3D(FVector((6.f + 22.f * F) / 50.f * (1.f + 0.08f * FMath::Sin(GetWorld()->GetTimeSeconds() * 24.f))));
			if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0))) { MID->SetVectorParameterValue(TEXT("Color"), Accent); MID->SetScalarParameterValue(TEXT("Opacity"), 0.55f + 0.4f * F); }
		}
	}
	else if (OrbComp.IsValid())
	{
		OrbComp->SetVisibility(false);
	}
	// uplink ring
	if (bRingOn && Actions && Actions->IsUplinkActive())
	{
		if (UStaticMeshComponent* C = Persistent(RingComp, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
		{
			const float T = GetWorld()->GetTimeSeconds();
			C->SetVisibility(true);
			C->SetWorldLocation(GetActorLocation() - FVector(0.f, 0.f, 88.f));
			C->SetWorldRotation(FRotator(0.f, T * 90.f, 0.f));
			C->SetWorldScale3D(FVector(1.8f + 0.1f * FMath::Sin(T * 6.f), 1.8f + 0.1f * FMath::Sin(T * 6.f), 0.01f));
			if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(C->GetMaterial(0))) { MID->SetVectorParameterValue(TEXT("Color"), Accent); MID->SetScalarParameterValue(TEXT("Opacity"), 0.6f); }
		}
	}
	else
	{
		bRingOn = bRingOn && Actions && Actions->IsUplinkActive();
		if (RingComp.IsValid()) RingComp->SetVisibility(false);
	}
	// beacon settling to the ground
	if (WorldBeacon.IsValid())
	{
		BeaconSettleTimer += Dt;
		const float U = FMath::Clamp(BeaconSettleTimer / 0.6f, 0.f, 1.f);
		const FVector From = BeaconSpawnTransform.GetLocation();
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(OperativeBeacon), false, this);
		FVector Ground = From - FVector(0.f, 0.f, 90.f);
		if (GetWorld()->LineTraceSingleByChannel(Hit, From + FVector(0.f, 0.f, 20.f), From - FVector(0.f, 0.f, 300.f), ECC_Visibility, Params) && Hit.bBlockingHit) Ground = Hit.ImpactPoint;
		const float E = U * U;
		WorldBeacon->SetActorLocation(FMath::Lerp(From, Ground, E));
		WorldBeacon->SetActorRotation(FMath::Lerp(BeaconSpawnTransform.Rotator(), FRotator(0.f, BeaconSpawnTransform.Rotator().Yaw + 90.f * U, 0.f), U));
	}
}

void AOperativeCharacter::ResetFx()
{
	bBeamOn = false;
	bRingOn = false;
	for (FFxItem& It : FxItems)
	{
		It.Life = 0.f;
		if (It.Comp.IsValid()) It.Comp->SetVisibility(false);
	}
	if (BeamComp.IsValid()) BeamComp->SetVisibility(false);
	if (OrbComp.IsValid()) OrbComp->SetVisibility(false);
	if (RingComp.IsValid()) RingComp->SetVisibility(false);
}
