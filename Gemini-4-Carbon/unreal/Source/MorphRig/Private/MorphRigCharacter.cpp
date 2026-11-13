#include "MorphRigCharacter.h"
#include "MorphRigAnimInstance.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/AudioComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Sound/SoundWave.h"
#include "DrawDebugHelpers.h"

AMorphRigCharacter::AMorphRigCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	// Standing character is 180.0 cm tall -> Capsule HalfHeight = 90.0 cm, Mesh Z = -90.0 cm
	GetCapsuleComponent()->InitCapsuleSize(34.0f, 90.0f);

	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->bRunPhysicsWithNoController = true; // Primary & crowd Operatives move without requiring Possession!
		MoveComp->bOrientRotationToMovement = false; // Travel velocity & facing are independently controlled!
		MoveComp->MaxWalkSpeed = 400.0f;
		MoveComp->MaxAcceleration = 2400.0f;
		MoveComp->BrakingDecelerationWalking = 2200.0f;
		MoveComp->GroundFriction = 8.0f;
		MoveComp->JumpZVelocity = 480.0f;
		MoveComp->AirControl = 0.45f;
		MoveComp->MaxStepHeight = 26.0f; // Supports 10/15/20 cm showcase steps cleanly
		MoveComp->SetWalkableFloorAngle(35.0f); // Supports 20-deg showcase slope cleanly
	}

	if (USkeletalMeshComponent* SkelComp = GetMesh())
	{
		SkelComp->SetRelativeLocation(FVector(0.0f, 0.0f, -90.0f));
		SkelComp->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
		SkelComp->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		SkelComp->bEnableUpdateRateOptimizations = false;
		SkelComp->SetBoundsScale(4.0f);
		SkelComp->bNeverDistanceCull = true;
	}

	DialogueAudioComp = CreateDefaultSubobject<UAudioComponent>(TEXT("DialogueAudioComp"));
	DialogueAudioComp->SetupAttachment(RootComponent);
	DialogueAudioComp->bAutoActivate = false;
	DialogueAudioComp->SetRelativeLocation(FVector(0.0f, 0.0f, 72.0f));

	// Secondary non-color geometric team markers above head (3D Diamond for Team A vs Double-Chevron for Team B)
	TeamIconMeshA = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TeamIconMeshA"));
	TeamIconMeshA->SetupAttachment(RootComponent);
	TeamIconMeshA->SetRelativeLocation(FVector(0.0f, 0.0f, 106.0f));
	TeamIconMeshA->SetRelativeRotation(FRotator(45.0f, 45.0f, 45.0f));
	TeamIconMeshA->SetRelativeScale3D(FVector(0.08f, 0.08f, 0.08f));
	TeamIconMeshA->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	TeamIconMeshA->CastShadow = false;

	TeamIconMeshB1 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TeamIconMeshB1"));
	TeamIconMeshB1->SetupAttachment(RootComponent);
	TeamIconMeshB1->SetRelativeLocation(FVector(0.0f, -6.0f, 107.0f));
	TeamIconMeshB1->SetRelativeRotation(FRotator(0.0f, 0.0f, -32.0f));
	TeamIconMeshB1->SetRelativeScale3D(FVector(0.055f, 0.115f, 0.035f));
	TeamIconMeshB1->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	TeamIconMeshB1->CastShadow = false;

	TeamIconMeshB2 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TeamIconMeshB2"));
	TeamIconMeshB2->SetupAttachment(RootComponent);
	TeamIconMeshB2->SetRelativeLocation(FVector(0.0f, +6.0f, 107.0f));
	TeamIconMeshB2->SetRelativeRotation(FRotator(0.0f, 0.0f, +32.0f));
	TeamIconMeshB2->SetRelativeScale3D(FVector(0.055f, 0.115f, 0.035f));
	TeamIconMeshB2->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	TeamIconMeshB2->CastShadow = false;

	DeployedBeaconVisual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DeployedBeaconVisual"));
	DeployedBeaconVisual->SetupAttachment(RootComponent);
	DeployedBeaconVisual->SetUsingAbsoluteLocation(true);
	DeployedBeaconVisual->SetUsingAbsoluteRotation(true);
	DeployedBeaconVisual->SetUsingAbsoluteScale(true);
	DeployedBeaconVisual->SetWorldScale3D(FVector(0.14f, 0.14f, 0.07f));
	DeployedBeaconVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	DeployedBeaconVisual->SetVisibility(false);
}

void AMorphRigCharacter::BeginPlay()
{
	Super::BeginPlay();

	SpawnOrigin = GetActorLocation();
	DesiredFacingYaw = GetActorRotation().Yaw;

	// Load Operative SkeletalMesh & AnimBlueprint / Native UMorphRigAnimInstance
	if (USkeletalMesh* OpMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/MorphRig/Character/Operative.Operative")))
	{
		GetMesh()->SetSkeletalMeshAsset(OpMesh);
	}

	AlignMeshForwardToActorX();

	UClass* AnimBPClass = LoadClass<UAnimInstance>(nullptr, TEXT("/Game/MorphRig/Character/ABP_Operative.ABP_Operative_C"));
	if (AnimBPClass && AnimBPClass->IsChildOf(UMorphRigAnimInstance::StaticClass()))
	{
		GetMesh()->SetAnimInstanceClass(AnimBPClass);
	}
	else
	{
		GetMesh()->SetAnimInstanceClass(UMorphRigAnimInstance::StaticClass());
	}

	if (USoundWave* DialogueWave = LoadObject<USoundWave>(nullptr, TEXT("/Game/MorphRig/Audio/SW_Dialogue.SW_Dialogue")))
	{
		DialogueAudioComp->SetSound(DialogueWave);
	}

	if (UStaticMesh* CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		TeamIconMeshA->SetStaticMesh(CubeMesh);
		TeamIconMeshB1->SetStaticMesh(CubeMesh);
		TeamIconMeshB2->SetStaticMesh(CubeMesh);
	}
	if (UStaticMesh* CylMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
	{
		DeployedBeaconVisual->SetStaticMesh(CylMesh);
	}

	InitDynamicMaterials();
	SetTeamVariant(TeamIndex, bShowSecondaryTeamCue);

	if (UMorphRigAnimInstance* AnimInst = GetMorphRigAnim())
	{
		AnimInst->OnMarkerFired.AddUniqueDynamic(this, &AMorphRigCharacter::HandleAnimMarkerFired);
	}
	UE_LOG(LogTemp, Display, TEXT("[MorphRig] Operative BeginPlay: Mesh=%s Anim=%s Loc=%s"),
		GetMesh() && GetMesh()->GetSkeletalMeshAsset() ? *GetMesh()->GetSkeletalMeshAsset()->GetName() : TEXT("NONE"),
		GetMorphRigAnim() ? *GetMorphRigAnim()->GetClass()->GetName() : TEXT("NONE"),
		*GetActorLocation().ToString());
}

void AMorphRigCharacter::AlignMeshForwardToActorX()
{
	USkeletalMesh* SkelMesh = GetMesh() ? GetMesh()->GetSkeletalMeshAsset() : nullptr;
	if (!SkelMesh)
	{
		return;
	}
	const FReferenceSkeleton& RefSkel = SkelMesh->GetRefSkeleton();
	const int32 FootIdx = RefSkel.FindBoneIndex(TEXT("foot_l"));
	const int32 BallIdx = RefSkel.FindBoneIndex(TEXT("ball_l"));
	if (FootIdx == INDEX_NONE || BallIdx == INDEX_NONE)
	{
		return;
	}
	auto CalcRefCS = [&RefSkel](int32 BoneIdx) -> FTransform
	{
		FTransform Acc = FTransform::Identity;
		int32 Cur = BoneIdx;
		while (Cur != INDEX_NONE)
		{
			Acc = Acc * RefSkel.GetRefBonePose()[Cur];
			Cur = RefSkel.GetParentIndex(Cur);
		}
		return Acc;
	};
	FVector ToeDir = CalcRefCS(BallIdx).GetLocation() - CalcRefCS(FootIdx).GetLocation();
	ToeDir.Z = 0.0f;
	if (!ToeDir.IsNearlyZero())
	{
		const float MeshForwardYawDeg = FMath::RadiansToDegrees(FMath::Atan2(ToeDir.Y, ToeDir.X));
		GetMesh()->SetRelativeRotation(FRotator(0.0f, -MeshForwardYawDeg, 0.0f));
	}
}

void AMorphRigCharacter::InitDynamicMaterials()
{
	TexArmorA_Base = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/CyberArmor_BaseColor.CyberArmor_BaseColor"));
	TexArmorA_Emis = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/CyberArmor_Emissive.CyberArmor_Emissive"));
	TexArmorB_Base = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/CyberArmor_TeamB_BaseColor.CyberArmor_TeamB_BaseColor"));
	TexArmorB_Emis = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/CyberArmor_TeamB_Emissive.CyberArmor_TeamB_Emissive"));

	TexPropsA_Base = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/PropsTech_BaseColor.PropsTech_BaseColor"));
	TexPropsA_Emis = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/PropsTech_Emissive.PropsTech_Emissive"));
	TexPropsB_Base = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/PropsTech_TeamB_BaseColor.PropsTech_TeamB_BaseColor"));
	TexPropsB_Emis = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/PropsTech_TeamB_Emissive.PropsTech_TeamB_Emissive"));

	USkeletalMeshComponent* SkelComp = GetMesh();
	if (!SkelComp) { return; }

	const int32 NumMats = SkelComp->GetNumMaterials();
	for (int32 Slot = 0; Slot < NumMats; ++Slot)
	{
		UMaterialInterface* BaseMat = SkelComp->GetMaterial(Slot);
		if (!BaseMat) { continue; }
		const FString MatName = BaseMat->GetName();
		if (MatName.Contains(TEXT("CyberArmor")) || Slot == 4)
		{
			MID_CyberArmor = SkelComp->CreateDynamicMaterialInstance(Slot, BaseMat);
		}
		else if (MatName.Contains(TEXT("Props_Tech")) || MatName.Contains(TEXT("PropsTech")) || Slot == 5)
		{
			MID_PropsTech = SkelComp->CreateDynamicMaterialInstance(Slot, BaseMat);
		}
	}

	if (UMaterialInterface* BasicMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")))
	{
		MID_TeamBadge = UMaterialInstanceDynamic::Create(BasicMat, this);
		TeamIconMeshA->SetMaterial(0, MID_TeamBadge);
		TeamIconMeshB1->SetMaterial(0, MID_TeamBadge);
		TeamIconMeshB2->SetMaterial(0, MID_TeamBadge);
		DeployedBeaconVisual->SetMaterial(0, MID_TeamBadge);
	}
}

void AMorphRigCharacter::SetTeamVariant(int32 NewTeamIndex, bool bEnableSecondaryCue)
{
	TeamIndex = (NewTeamIndex == 0) ? 0 : 1;
	bShowSecondaryTeamCue = bEnableSecondaryCue;

	const bool bTeamB = (TeamIndex == 1);
	const FLinearColor AccentColor = bTeamB
		? FLinearColor(1.0f, 0.22f, 0.06f, 1.0f)   // Team B Crimson-Amber
		: FLinearColor(0.0f, 0.82f, 1.0f, 1.0f);   // Team A Vanguard Cyan

	if (MID_CyberArmor)
	{
		if (UTexture2D* BaseT = bTeamB ? TexArmorB_Base.Get() : TexArmorA_Base.Get())
		{
			MID_CyberArmor->SetTextureParameterValue(TEXT("BaseColorTex"), BaseT);
		}
		if (UTexture2D* EmisT = bTeamB ? TexArmorB_Emis.Get() : TexArmorA_Emis.Get())
		{
			MID_CyberArmor->SetTextureParameterValue(TEXT("EmissiveTex"), EmisT);
		}
		MID_CyberArmor->SetVectorParameterValue(TEXT("TeamRimColor"), AccentColor);
		MID_CyberArmor->SetScalarParameterValue(TEXT("OutlineStrength"), bShowSecondaryTeamCue ? 1.0f : 0.0f);
	}

	if (MID_PropsTech)
	{
		if (UTexture2D* BaseT = bTeamB ? TexPropsB_Base.Get() : TexPropsA_Base.Get())
		{
			MID_PropsTech->SetTextureParameterValue(TEXT("BaseColorTex"), BaseT);
		}
		if (UTexture2D* EmisT = bTeamB ? TexPropsB_Emis.Get() : TexPropsA_Emis.Get())
		{
			MID_PropsTech->SetTextureParameterValue(TEXT("EmissiveTex"), EmisT);
		}
		MID_PropsTech->SetVectorParameterValue(TEXT("TeamRimColor"), AccentColor);
		MID_PropsTech->SetScalarParameterValue(TEXT("OutlineStrength"), bShowSecondaryTeamCue ? 1.0f : 0.0f);
	}

	if (MID_TeamBadge)
	{
		MID_TeamBadge->SetVectorParameterValue(TEXT("Color"), AccentColor);
	}

	TeamIconMeshA->SetVisibility(bShowSecondaryTeamCue && !bTeamB);
	TeamIconMeshB1->SetVisibility(bShowSecondaryTeamCue && bTeamB);
	TeamIconMeshB2->SetVisibility(bShowSecondaryTeamCue && bTeamB);
}

void AMorphRigCharacter::SetForcedLODMode(int32 LODMode)
{
	ForcedLODSelection = FMath::Clamp(LODMode, -1, 2);
	if (USkeletalMeshComponent* SkelComp = GetMesh())
	{
		// UE SetForcedLOD: 0 = Automatic, 1 = LOD0, 2 = LOD1, 3 = LOD2
		SkelComp->SetForcedLOD((ForcedLODSelection < 0) ? 0 : (ForcedLODSelection + 1));
	}
}

int32 AMorphRigCharacter::GetCurrentDisplayedLOD() const
{
	return GetMesh() ? GetMesh()->GetPredictedLODLevel() : 0;
}

UMorphRigAnimInstance* AMorphRigCharacter::GetMorphRigAnim() const
{
	return GetMesh() ? Cast<UMorphRigAnimInstance>(GetMesh()->GetAnimInstance()) : nullptr;
}

void AMorphRigCharacter::TriggerDialoguePerformance()
{
	if (UMorphRigAnimInstance* AnimInst = GetMorphRigAnim())
	{
		if (AnimInst->TriggerSocialOrDialogue(TEXT("dialogue")))
		{
			if (DialogueAudioComp && DialogueAudioComp->GetSound())
			{
				DialogueAudioComp->Stop();
				DialogueAudioComp->SetPitchMultiplier(AnimInst->ActionPlayRate);
				DialogueAudioComp->Play(0.0f);
			}
		}
	}
}

void AMorphRigCharacter::ResetOperativeFull(const FVector& ResetWorldLocation, float ResetYaw)
{
	if (DialogueAudioComp && DialogueAudioComp->IsPlaying())
	{
		DialogueAudioComp->Stop();
	}
	DeployedBeaconVisual->SetVisibility(false);
	DesiredMoveInput = FVector2D::ZeroVector;
	KnockbackRemainingSpeed = 0.0f;
	PrevDashTime = 0.0f;
	DesiredFacingYaw = ResetYaw;

	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->StopMovementImmediately();
	}
	SetActorLocationAndRotation(ResetWorldLocation, FRotator(0.0f, ResetYaw, 0.0f), false, nullptr, ETeleportType::TeleportPhysics);

	if (UMorphRigAnimInstance* AnimInst = GetMorphRigAnim())
	{
		AnimInst->ResetToReadyState();
	}
}

void AMorphRigCharacter::HandleAnimMarkerFired(const FMorphRigEventRecord& EventRec)
{
	// 1. Blink actor teleport is driven by the teleport_event marker, NOT baked root travel (SPEC §8)
	if (EventRec.MarkerName == TEXT("teleport_event") && EventRec.ClipId == TEXT("blink_out"))
	{
		const FVector BlinkStep = GetActorForwardVector() * 260.0f;
		AddActorWorldOffset(BlinkStep, true);
	}
	// 2. Deploy places a visible small beacon prop on the floor at beacon_release!
	else if (EventRec.MarkerName == TEXT("beacon_release") && EventRec.ClipId == TEXT("deploy"))
	{
		const FVector HandWorld = GetMesh()->DoesSocketExist(TEXT("socket_hand_l"))
			? GetMesh()->GetSocketLocation(TEXT("socket_hand_l"))
			: (GetActorLocation() + GetActorForwardVector() * 45.0f - FVector(0, 0, 86.0f));
		DeployedBeaconVisual->SetWorldLocation(FVector(HandWorld.X, HandWorld.Y, GetActorLocation().Z - 86.5f));
		DeployedBeaconVisual->SetWorldRotation(FRotator::ZeroRotator);
		DeployedBeaconVisual->SetVisibility(true);
	}
	// 3. Ranged fire / burst / cast / charge muzzle visual pulse
	else if (EventRec.MarkerName == TEXT("muzzle_fire") ||
		EventRec.MarkerName == TEXT("muzzle_fire_1") ||
		EventRec.MarkerName == TEXT("muzzle_fire_2") ||
		EventRec.MarkerName == TEXT("muzzle_fire_3") ||
		EventRec.MarkerName == TEXT("cast_release") ||
		EventRec.MarkerName == TEXT("charge_release") ||
		EventRec.MarkerName == TEXT("beam_tick"))
	{
		MuzzleFlashTimer = 0.14f;
		LastMuzzleOrigin = GetMesh()->DoesSocketExist(TEXT("socket_emitter_muzzle"))
			? GetMesh()->GetSocketLocation(TEXT("socket_emitter_muzzle"))
			: (GetActorLocation() + GetActorForwardVector() * 55.0f + FVector(0, 0, 40.0f));
	}
}

void AMorphRigCharacter::TickCrowdBehavior(float DeltaSeconds)
{
	UMorphRigAnimInstance* AnimInst = GetMorphRigAnim();
	if (!AnimInst || !GetWorld()) { return; }

	const float T = GetWorld()->GetTimeSeconds() + CrowdRoleIndex * 1.37f;
	WorldAimTarget = GetActorLocation() + FVector(
		260.0f * FMath::Cos(T * 0.9f),
		180.0f * FMath::Sin(T * 1.1f),
		45.0f + 55.0f * FMath::Sin(T * 1.4f));

	switch (CrowdRoleIndex % 5)
	{
	case 0: // 8-dir strafing + ranged burst (bounded around SpawnOrigin)
		SpeedTier = 1;
		{
			const FVector Drift = GetActorLocation() - SpawnOrigin;
			if (Drift.Size2D() > 85.0f)
			{
				const FVector BackLocal = GetActorRotation().UnrotateVector(-Drift.GetSafeNormal2D());
				DesiredMoveInput = FVector2D(BackLocal.X, BackLocal.Y) * 0.55f;
			}
			else
			{
				DesiredMoveInput = FVector2D(FMath::Cos(T * 1.6f) * 0.55f, FMath::Sin(T * 1.6f) * 0.55f);
			}
		}
		if (FMath::Fmod(T, 2.4f) < DeltaSeconds * 1.5f)
		{
			AnimInst->TriggerUpperBodyAction(EMorphRigUpperBodyMode::RangedBurst);
		}
		break;
	case 1: // Melee 1-2-3 combo cadence
		DesiredMoveInput = FVector2D::ZeroVector;
		if (FMath::Fmod(T, 1.35f) < DeltaSeconds * 1.5f)
		{
			AnimInst->TriggerMeleeAttack();
		}
		break;
	case 2: // Channel -> interrupt -> charge -> release cycle
		DesiredMoveInput = FVector2D::ZeroVector;
		if (AnimInst->PrimaryState == EMorphRigPrimaryState::Locomotion)
		{
			if (((int32)T % 2) == 0) { AnimInst->StartChannel(1.4f); }
			else { AnimInst->StartCharge(); }
		}
		else if (AnimInst->PrimaryState == EMorphRigPrimaryState::ChargeHold && AnimInst->SustainedHoldTimer > 0.9f)
		{
			AnimInst->ReleaseCharge();
		}
		break;
	case 3: // Reload & Deploy prop contact demonstration
		DesiredMoveInput = FVector2D::ZeroVector;
		if (AnimInst->PrimaryState == EMorphRigPrimaryState::Locomotion)
		{
			if (((int32)(T * 0.5f) % 2) == 0) { AnimInst->TriggerReload(); }
			else { AnimInst->TriggerDeploy(); }
		}
		break;
	case 4: // Walk/Sprint cycle with additive hit reactions (bounded around SpawnOrigin)
	default:
		SpeedTier = (((int32)(T * 0.4f) % 2) == 0) ? 0 : 1;
		{
			const FVector Drift = GetActorLocation() - SpawnOrigin;
			if (Drift.Size2D() > 85.0f)
			{
				const FVector BackLocal = GetActorRotation().UnrotateVector(-Drift.GetSafeNormal2D());
				DesiredMoveInput = FVector2D(BackLocal.X, BackLocal.Y) * 0.5f;
			}
			else
			{
				DesiredMoveInput = FVector2D(0.0f, FMath::Cos(T * 1.8f) * 0.55f);
			}
		}
		if (FMath::Fmod(T, 2.1f) < DeltaSeconds * 1.5f)
		{
			AnimInst->TriggerAdditiveHit(TEXT("f"));
		}
		break;
	}
}

void AMorphRigCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	UMorphRigAnimInstance* AnimInst = GetMorphRigAnim();
	UCharacterMovementComponent* MoveComp = GetCharacterMovement();
	if (!AnimInst || !MoveComp)
	{
		return;
	}

	if (bIsCrowdInstance)
	{
		TickCrowdBehavior(DeltaSeconds);
	}

	// Stop dialogue audio immediately if interrupted by death/stun/state change
	if (DialogueAudioComp && DialogueAudioComp->IsPlaying())
	{
		if (AnimInst->PrimaryClip != TEXT("dialogue"))
		{
			DialogueAudioComp->Stop();
		}
		else
		{
			DialogueAudioComp->SetPitchMultiplier(AnimInst->ActionPlayRate);
		}
	}

	// 1. Root-Motion Dash Capsule Tracking (nominal 200 cm horizontal travel!)
	if (AnimInst->PrimaryState == EMorphRigPrimaryState::MobilityDash)
	{
		if (AnimInst->PrimaryTime < PrevDashTime)
		{
			PrevDashTime = 0.0f;
		}
		const FVector LocalDelta = AnimInst->ConsumeDashRootDeltaCm(PrevDashTime, AnimInst->PrimaryTime, AnimInst->PrimaryClip);
		PrevDashTime = AnimInst->PrimaryTime;
		if (!LocalDelta.IsNearlyZero())
		{
			const FVector WorldDelta = GetActorRotation().RotateVector(LocalDelta);
			AddActorWorldOffset(WorldDelta, true);
		}
	}
	else
	{
		PrevDashTime = 0.0f;
	}

	// 2. Host-Driven Knockback Forced Travel
	if (AnimInst->PrimaryState == EMorphRigPrimaryState::DisableKnockback)
	{
		const float U = FMath::Clamp(AnimInst->PrimaryTime / FMath::Max(0.2f, AnimInst->PrimaryDuration), 0.0f, 1.0f);
		const float PushSpeed = 360.0f * (1.0f - U);
		AddActorWorldOffset(-GetActorForwardVector() * (PushSpeed * DeltaSeconds), true);
	}

	// 3. Soft CC Travel Overrides (Fear flees target; Charm & Taunt approach target)
	FVector2D EffectiveMove = DesiredMoveInput;
	int32 EffectiveTier = SpeedTier;
	float EffectiveFacingYaw = DesiredFacingYaw;

	const FVector ToAim = WorldAimTarget - GetActorLocation();
	if (!ToAim.IsNearlyZero())
	{
		const float YawToTarget = FMath::RadiansToDegrees(FMath::Atan2(ToAim.Y, ToAim.X));
		if (AnimInst->bFeared)
		{
			EffectiveFacingYaw = FRotator::NormalizeAxis(YawToTarget + 180.0f);
			EffectiveMove = FVector2D(1.0f, 0.0f);
			EffectiveTier = 0; // Walk away
		}
		else if (AnimInst->bCharmed)
		{
			EffectiveFacingYaw = YawToTarget;
			EffectiveMove = (ToAim.Size2D() > 120.0f) ? FVector2D(1.0f, 0.0f) : FVector2D::ZeroVector;
			EffectiveTier = 0; // Walk toward source
		}
		else if (AnimInst->bTaunted)
		{
			EffectiveFacingYaw = YawToTarget;
			EffectiveMove = (ToAim.Size2D() > 110.0f) ? FVector2D(1.0f, 0.0f) : FVector2D::ZeroVector;
			EffectiveTier = 1; // Run toward taunter
		}
	}

	// 4. Independent Facing Rotation + Turn-in-Place 90 Detection
	if (AnimInst->AllowsLocomotionInput() || AnimInst->bRooted)
	{
		const float CurrYaw = GetActorRotation().Yaw;
		const float DeltaYaw = FMath::FindDeltaAngleDegrees(CurrYaw, EffectiveFacingYaw);
		const float NewYaw = FMath::FInterpTo(CurrYaw, CurrYaw + DeltaYaw, DeltaSeconds, 10.0f);
		SetActorRotation(FRotator(0.0f, NewYaw, 0.0f));

		if (AnimInst->GroundSpeed < 10.0f && AnimInst->LocoSubClip == NAME_None && FMath::Abs(DeltaYaw) > 65.0f)
		{
			AnimInst->TriggerLocoTransition((DeltaYaw < 0.0f) ? TEXT("turn_l90") : TEXT("turn_r90"));
		}
	}

	// 5. Apply Nominal Reference Speeds: 150 cm/s Walk, 400 cm/s Run, 650 cm/s Forward Sprint (SPEC §8)
	const float TargetMaxSpeed = (EffectiveTier == 0) ? 150.0f : ((EffectiveTier == 1) ? 400.0f : 650.0f);
	MoveComp->MaxWalkSpeed = TargetMaxSpeed * AnimInst->ActionPlayRate;

	if (AnimInst->AllowsLocomotionInput() && !EffectiveMove.IsNearlyZero(0.02f))
	{
		const FVector ClampedInput = FVector(EffectiveMove.X, EffectiveMove.Y, 0.0f).GetClampedToMaxSize(1.0f);
		const FVector WorldDir = GetActorRotation().RotateVector(ClampedInput);
		AddMovementInput(WorldDir, 1.0f, /*bForce=*/true);
	}

	// 6. Feed Velocity, Groundedness, Start/Stop/Pivot Triggers, and Aim Angles to AnimInstance
	const FVector Vel = GetVelocity();
	const FVector VelXY(Vel.X, Vel.Y, 0.0f);
	const float SpeedXY = VelXY.Size();
	const FVector LocalVel = GetActorRotation().UnrotateVector(VelXY);

	// Automatic Start / Stop / 180-Pivot sub-clip triggers
	if (AnimInst->PrimaryState == EMorphRigPrimaryState::Locomotion && AnimInst->bIsGrounded && AnimInst->LocoSubClip == NAME_None)
	{
		if (PrevIdleSpeed < 12.0f && SpeedXY > 95.0f && LocalVel.X > 50.0f)
		{
			AnimInst->TriggerLocoTransition(TEXT("start_f"));
		}
		else if (PrevIdleSpeed > 180.0f && SpeedXY < 25.0f && EffectiveMove.IsNearlyZero())
		{
			AnimInst->TriggerLocoTransition(TEXT("stop_f"));
		}
		else if (SpeedXY > 160.0f && !PrevTravelDir.IsNearlyZero())
		{
			const FVector CurrDir = VelXY.GetSafeNormal();
			if (FVector::DotProduct(PrevTravelDir, CurrDir) < -0.70f)
			{
				const float CrossZ = FVector::CrossProduct(PrevTravelDir, CurrDir).Z;
				AnimInst->TriggerLocoTransition((CrossZ < 0.0f) ? TEXT("pivot_l180") : TEXT("pivot_r180"));
			}
		}
	}
	if (SpeedXY > 80.0f)
	{
		PrevTravelDir = VelXY.GetSafeNormal();
	}
	PrevIdleSpeed = SpeedXY;

	AnimInst->GroundSpeed = SpeedXY;
	AnimInst->LocalVelForward = LocalVel.X;
	AnimInst->LocalVelRight = LocalVel.Y;
	AnimInst->bIsGrounded = !MoveComp->IsFalling();
	AnimInst->LookAtTargetWorld = WorldAimTarget;

	// Compute Aim Grid Yaw [-60..+60] (-60=Left, +60=Right) & Pitch [-35..+35] (-35=Down, +35=Up)
	const FVector ChestWorld = GetActorLocation() + FVector(0.0f, 0.0f, 45.0f);
	const FVector AimVecWorld = (WorldAimTarget - ChestWorld);
	if (AimVecWorld.SizeSquared() > 400.0f)
	{
		const FVector AimLocal = GetActorRotation().UnrotateVector(AimVecWorld.GetSafeNormal());
		// In UE Character space: +X is Forward, +Y is Right (-Y is Left), +Z is Up
		const float RawYawDeg = FMath::RadiansToDegrees(FMath::Atan2(AimLocal.Y, AimLocal.X));
		const float RawPitchDeg = FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(AimLocal.Z, -1.0f, 1.0f)));
		AnimInst->AimYawDeg = FMath::FInterpTo(AnimInst->AimYawDeg, FMath::Clamp(RawYawDeg, -60.0f, 60.0f), DeltaSeconds, 12.0f);
		AnimInst->AimPitchDeg = FMath::FInterpTo(AnimInst->AimPitchDeg, FMath::Clamp(RawPitchDeg, -35.0f, 35.0f), DeltaSeconds, 12.0f);
	}

	// 7. Optional Muzzle / Beam Presentation Line & Skeleton Debug Overlay
	if (MuzzleFlashTimer > 0.0f && GetWorld())
	{
		MuzzleFlashTimer -= DeltaSeconds;
		const FColor BeamCol = (TeamIndex == 0) ? FColor(0, 220, 255) : FColor(255, 85, 30);
		DrawDebugLine(GetWorld(), LastMuzzleOrigin, WorldAimTarget, BeamCol, false, -1.0f, 0, 2.2f);
		DrawDebugSphere(GetWorld(), LastMuzzleOrigin, 5.5f, 8, BeamCol, false, -1.0f, 0, 1.5f);
	}
	if (AnimInst->PrimaryState == EMorphRigPrimaryState::ChannelLoop && GetWorld() && GetMesh()->DoesSocketExist(TEXT("socket_emitter_muzzle")))
	{
		const FVector MuzzlePos = GetMesh()->GetSocketLocation(TEXT("socket_emitter_muzzle"));
		const FColor BeamCol = (TeamIndex == 0) ? FColor(0, 230, 255) : FColor(255, 95, 35);
		DrawDebugLine(GetWorld(), MuzzlePos, WorldAimTarget, BeamCol, false, -1.0f, 0, 3.0f);
	}

	if (bShowSkeletonOverlay)
	{
		DrawSkeletonAndSocketsDebug();
	}
}

void AMorphRigCharacter::DrawSkeletonAndSocketsDebug() const
{
	UWorld* World = GetWorld();
	USkeletalMeshComponent* SkelComp = GetMesh();
	USkeletalMesh* SkelMesh = SkelComp ? SkelComp->GetSkeletalMeshAsset() : nullptr;
	if (!World || !SkelComp || !SkelMesh)
	{
		return;
	}

	const FReferenceSkeleton& RefSkel = SkelMesh->GetRefSkeleton();
	const int32 NumBones = RefSkel.GetNum();
	for (int32 i = 0; i < NumBones; ++i)
	{
		const int32 ParIdx = RefSkel.GetParentIndex(i);
		const FVector ChildPos = SkelComp->GetBoneLocation(RefSkel.GetBoneName(i));
		if (ParIdx != INDEX_NONE)
		{
			const FVector ParPos = SkelComp->GetBoneLocation(RefSkel.GetBoneName(ParIdx));
			DrawDebugLine(World, ParPos, ChildPos, FColor(60, 255, 160), false, -1.0f, SDPG_Foreground, 0.9f);
		}
		DrawDebugPoint(World, ChildPos, 4.0f, FColor(255, 220, 60), false, -1.0f, SDPG_Foreground);
	}

	static const FName SocketNames[] = {
		TEXT("socket_hand_r"), TEXT("socket_hand_l"), TEXT("socket_emitter_muzzle"),
		TEXT("socket_blade_base"), TEXT("socket_blade_tip"), TEXT("socket_cell_slot"),
		TEXT("socket_beacon_dock"), TEXT("socket_chest_fx"), TEXT("socket_head_fx"), TEXT("socket_root_fx")
	};
	for (const FName& SName : SocketNames)
	{
		if (SkelComp->DoesSocketExist(SName))
		{
			const FTransform ST = SkelComp->GetSocketTransform(SName);
			DrawDebugCoordinateSystem(World, ST.GetLocation(), ST.Rotator(), 9.0f, false, -1.0f, SDPG_Foreground, 1.2f);
		}
	}
}
