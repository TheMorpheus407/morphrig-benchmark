#include "OperativeCharacter.h"
#include "MorphRig.h"
#include "MorphRigData.h"
#include "OperativeAnimInstance.h"
#include "OperativeMovementComponent.h"
#include "ShowcaseFX.h"
#include "AnimationRuntime.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundBase.h"

namespace
{
	const FLinearColor TeamColors[2] = { FLinearColor(0.0f, 0.62f, 1.0f), FLinearColor(1.0f, 0.36f, 0.02f) };

	FString SlotShortName(FName Slot)
	{
		FString S = Slot.ToString();
		S.RemoveFromStart(TEXT("M_"));
		return S;
	}
}

AOperativeCharacter::AOperativeCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UOperativeMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = true;
	bUseControllerRotationYaw = false;
	GetCapsuleComponent()->InitCapsuleSize(30.f, 90.f);

	USkeletalMeshComponent* SkelMesh = GetMesh();
	SkelMesh->SetRelativeLocation(FVector(0, 0, -92.f));   // capsule half height 90 + the ~2 cm the movement component floats above the floor
	SkelMesh->SetRelativeRotation(FRotator(0, -90.f, 0));   // mesh faces +Y, the actor faces +X
	SkelMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SkelMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	SkelMesh->bEnableUpdateRateOptimizations = false;
	SkelMesh->SetAnimationMode(EAnimationMode::AnimationBlueprint);
	SkelMesh->SetAnimInstanceClass(UOperativeAnimInstance::StaticClass());

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = false;
	Move->MaxWalkSpeed = 400.f;
	Move->MaxAcceleration = 1900.f;
	Move->BrakingDecelerationWalking = 1700.f;
	Move->GroundFriction = 8.f;
	Move->JumpZVelocity = 520.f;
	Move->GravityScale = 1.5f;
	Move->AirControl = 0.4f;
	Move->MaxStepHeight = 30.f;
	Move->SetWalkableFloorAngle(40.f);
	Move->bUseFlatBaseForFloorChecks = false;
	Move->bRunPhysicsWithNoController = true;   // instances are driven by the state component, not by a possessing controller

	StateComp = CreateDefaultSubobject<UOperativeStateComponent>(TEXT("State"));

	Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	Voice->SetupAttachment(GetMesh());
	Voice->bAutoActivate = false;
	Voice->bIsUISound = false;

	TeamRing = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TeamRing"));
	TeamRing->SetupAttachment(GetCapsuleComponent());
	TeamRing->SetRelativeLocation(FVector(0, 0, -90.5f));
	TeamRing->SetRelativeRotation(FRotator(0, -90.f, 0));
	TeamRing->SetRelativeScale3D(FVector(1.35f));
	TeamRing->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	TeamRing->SetCastShadow(false);

	BladeGlow = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BladeGlow"));
	BladeGlow->SetupAttachment(GetMesh());
	BladeGlow->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BladeGlow->SetCastShadow(false);
	BladeGlow->SetVisibility(false);
}

void AOperativeCharacter::BeginPlay()
{
	// assets are referenced by path so that a re-import never needs a code or blueprint change
	if (USkeletalMesh* SK = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Operative/Mesh/SK_Operative.SK_Operative")))
	{
		GetMesh()->SetSkeletalMesh(SK);
		const FReferenceSkeleton& Ref = SK->GetRefSkeleton();
		TArray<FTransform> CS;
		FAnimationRuntime::FillUpComponentSpaceTransforms(Ref, Ref.GetRefBonePose(), CS);
		const int32 Head = Ref.FindBoneIndex(TEXT("head"));
		if (CS.IsValidIndex(Head))
		{
			HeadForwardLocal = CS[Head].GetRotation().UnrotateVector(FVector(0, 1, 0));
		}
	}
	else
	{
		UE_LOG(LogMorphRig, Error, TEXT("SK_Operative is missing - run tools/ue_import.sh"));
	}
	if (UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane")))
	{
		TeamRing->SetStaticMesh(Plane);
	}
	if (UMaterialInterface* RingMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Showcase/M_TeamRing.M_TeamRing")))
	{
		RingMid = UMaterialInstanceDynamic::Create(RingMat, this);
		TeamRing->SetMaterial(0, RingMid);
	}
	if (UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		BladeGlow->SetStaticMesh(Cube);
		if (UMaterialInterface* Fx = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Showcase/M_FX.M_FX")))
		{
			BladeMid = UMaterialInstanceDynamic::Create(Fx, this);
			BladeMid->SetScalarParameterValue(TEXT("Opacity"), 0.55f);
			BladeMid->SetScalarParameterValue(TEXT("Intensity"), 14.f);
			BladeGlow->SetMaterial(0, BladeMid);
		}
	}
	if (USoundBase* Snd = LoadObject<USoundBase>(nullptr, TEXT("/Game/Operative/Audio/dialogue.dialogue")))
	{
		Voice->SetSound(Snd);
	}
	Super::BeginPlay();
	SpawnLocation = GetActorLocation();
	SpawnYaw = (float)GetActorRotation().Yaw;
	if (ViewerLocation.IsZero())
	{
		ViewerLocation = SpawnLocation;
	}
	ApplyMaterials();
	SetRing(bRing);
	StateComp->OnEvent.AddUObject(this, &AOperativeCharacter::HandleEvent);
}

void AOperativeCharacter::Landed(const FHitResult& Hit)
{
	Super::Landed(Hit);
	const float Impact = FMath::Abs((float)GetCharacterMovement()->Velocity.Z);
	StateComp->NotifyLanded(Impact);
}

FLinearColor AOperativeCharacter::GetTeamColor() const
{
	return TeamColors[FMath::Clamp(Team, 0, 1)];
}

// ------------------------------------------------------------------------------------------------ materials / presentation
void AOperativeCharacter::ApplyMaterials()
{
	USkeletalMeshComponent* SkelMesh = GetMesh();
	const TArray<FName> Slots = SkelMesh->GetMaterialSlotNames();
	SlotMids.Reset();
	const TCHAR* TeamSuffix = Team == 0 ? TEXT("TeamA") : TEXT("TeamB");
	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		const FString Short = SlotShortName(Slots[i]);
		const FString Path = FString::Printf(TEXT("/Game/Operative/Materials/MI_Operative_%s_%s.MI_Operative_%s_%s"), *Short, TeamSuffix, *Short, TeamSuffix);
		UMaterialInterface* TeamMat = LoadObject<UMaterialInterface>(nullptr, *Path);
		UMaterialInterface* Use = TeamMat;
		if (DisplayMode == EOpDisplayMode::Wireframe)
		{
			Use = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Operative/Materials/M_Debug_Wireframe.M_Debug_Wireframe"));
		}
		else if (DisplayMode == EOpDisplayMode::Clay)
		{
			Use = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Operative/Materials/M_Debug_Clay.M_Debug_Clay"));
		}
		else if (DisplayMode == EOpDisplayMode::Normals)
		{
			Use = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Operative/Materials/M_Debug_Normals.M_Debug_Normals"));
		}
		if (!Use)
		{
			SlotMids.Add(nullptr);
			continue;
		}
		UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(Use, this);
		if (DisplayMode == EOpDisplayMode::Normals && TeamMat)
		{
			UTexture* Normal = nullptr;
			if (TeamMat->GetTextureParameterValue(FHashedMaterialParameterInfo(TEXT("NormalTex")), Normal) && Normal)
			{
				Mid->SetTextureParameterValue(TEXT("NormalTex"), Normal);
			}
		}
		SkelMesh->SetMaterial(i, Mid);
		SlotMids.Add(Mid);
	}
	if (RingMid)
	{
		RingMid->SetVectorParameterValue(TEXT("Color"), GetTeamColor());
		RingMid->SetScalarParameterValue(TEXT("Style"), (float)Team);
	}
	if (BladeMid)
	{
		BladeMid->SetVectorParameterValue(TEXT("Color"), GetTeamColor());
	}
	SetOutline(bOutline);
}

void AOperativeCharacter::SetTeam(int32 InTeam)
{
	Team = FMath::Clamp(InTeam, 0, 1);
	ApplyMaterials();
}

void AOperativeCharacter::SetOutline(bool bOn)
{
	bOutline = bOn;
	if (bOn)
	{
		if (!OutlineMid)
		{
			if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Operative/Materials/M_Outline.M_Outline")))
			{
				OutlineMid = UMaterialInstanceDynamic::Create(M, this);
			}
		}
		if (OutlineMid)
		{
			OutlineMid->SetVectorParameterValue(TEXT("OutlineColor"), GetTeamColor());
			OutlineMid->SetScalarParameterValue(TEXT("Dashed"), Team == 0 ? 0.f : 1.f);
			GetMesh()->SetOverlayMaterial(OutlineMid);
		}
	}
	else
	{
		GetMesh()->SetOverlayMaterial(nullptr);
	}
}

void AOperativeCharacter::SetRing(bool bOn)
{
	bRing = bOn;
	TeamRing->SetVisibility(bOn && !bHiddenForBlink);
}

void AOperativeCharacter::SetDisplayMode(EOpDisplayMode Mode)
{
	DisplayMode = Mode;
	ApplyMaterials();
}

void AOperativeCharacter::SetLodMode(int32 Mode)
{
	LodMode = FMath::Clamp(Mode, 0, 3);
	GetMesh()->SetForcedLOD(LodMode);
}

int32 AOperativeCharacter::GetCurrentLod() const
{
	return GetMesh()->GetPredictedLODLevel();
}

void AOperativeCharacter::SetMeshHiddenForBlink(bool bHidden)
{
	bHiddenForBlink = bHidden;
	GetMesh()->SetVisibility(!bHidden, false);
	TeamRing->SetVisibility(bRing && !bHidden);
	if (bHidden)
	{
		Dissolve = 1.f;
		DissolveTarget = 1.f;
	}
	else
	{
		DissolveTarget = 0.f;
		DissolveSpeed = 5.f;
	}
}

void AOperativeCharacter::OnRespawned()
{
	if (WorldBeacon)
	{
		WorldBeacon->Destroy();
		WorldBeacon = nullptr;
	}
	if (AShowcaseFX* FX = AShowcaseFX::Get(GetWorld()))
	{
		FX->ClearPersistent(FName(*FString::Printf(TEXT("beam_%d"), InstanceIndex)));
		FX->ClearPersistent(FName(*FString::Printf(TEXT("charge_%d"), InstanceIndex)));
	}
	StopDialogueAudio();
	HitFlash = 0.f;
	Dissolve = 1.f;
	DissolveTarget = 0.f;
	DissolveSpeed = 1.3f;
	BladeGlow->SetVisibility(false);
}

void AOperativeCharacter::PlayDialogueAudio(float StartTime)
{
	if (Voice && Voice->Sound)
	{
		Voice->Play(FMath::Max(0.f, StartTime));
	}
}

void AOperativeCharacter::StopDialogueAudio()
{
	if (Voice && Voice->IsPlaying())
	{
		Voice->Stop();
	}
}

bool AOperativeCharacter::IsDialogueAudioPlaying() const
{
	return Voice && Voice->IsPlaying();
}

float AOperativeCharacter::GetContactError(FName& OutProp, FName& OutHolder) const
{
	// distance between a manipulated prop and the socket of the hand that holds it according to the clip's prop track
	const FOpClipPlay* Plays[2] = { &StateComp->GetBaseClip(), &StateComp->GetUpperClip() };
	for (const FOpClipPlay* P : Plays)
	{
		if (!P->IsValid())
		{
			continue;
		}
		for (const FMorphPropSegment& Seg : P->Info->PropSegments)
		{
			if (P->Time >= Seg.Start && P->Time <= Seg.End && GetMesh()->GetBoneIndex(Seg.Holder) != INDEX_NONE)
			{
				OutProp = Seg.Prop;
				OutHolder = Seg.Holder;
				const FName Socket = Seg.Holder == FName(TEXT("hand_l")) ? FName(TEXT("hand_l_socket")) :
					(Seg.Holder == FName(TEXT("hand_r")) ? FName(TEXT("hand_r_socket")) : Seg.Holder);
				return (float)FVector::Dist(GetMesh()->GetSocketLocation(Seg.Prop), GetMesh()->GetSocketLocation(Socket));
			}
		}
	}
	return -1.f;
}

// ------------------------------------------------------------------------------------------------ event driven effects
void AOperativeCharacter::HandleEvent(UOperativeStateComponent* Comp, const FOpClipPlay& Play, FName Event)
{
	AShowcaseFX* FX = AShowcaseFX::Get(GetWorld());
	if (!FX)
	{
		return;
	}
	const FString E = Event.ToString();
	const FLinearColor Col = GetTeamColor();
	USkeletalMeshComponent* SkelMesh = GetMesh();
	const bool bViewer = Comp->GetState() == EOpState::Viewer;
	const FVector Muzzle = SkelMesh->GetSocketLocation(TEXT("emitter_muzzle"));
	FVector AimPoint = Comp->Input.bHasAimPoint && !bViewer ? Comp->Input.AimPoint : Muzzle + SkelMesh->GetSocketQuaternion(TEXT("emitter_muzzle")).GetForwardVector() * 800.0;
	const FVector Dir = (AimPoint - Muzzle).GetSafeNormal();
	if (E.StartsWith(TEXT("muzzle_")))
	{
		FX->Spawn(AShowcaseFX::Sphere, Muzzle, FRotator::ZeroRotator, FVector(0.22f), FVector(0.05f), Col, 0.09f, FVector::ZeroVector, 30.f, 0.9f, 0.f);
		FX->Spawn(AShowcaseFX::Sphere, Muzzle, FRotator::ZeroRotator, FVector(0.09f), FVector(0.09f), Col, 0.5f, Dir * 3200.0, 22.f, 0.95f, 0.6f);
	}
	else if (Event == FName(TEXT("cast_release")))
	{
		if (Play.Id() == FName(TEXT("cast_directional")))
		{
			FX->Spawn(AShowcaseFX::Sphere, Muzzle, FRotator::ZeroRotator, FVector(0.3f), FVector(0.42f), Col, 0.9f, Dir * 1500.0, 14.f, 0.85f, 0.2f);
		}
		else if (Play.Id() == FName(TEXT("cast_ground")))
		{
			FVector Ground = AimPoint;
			Ground.Z = GetActorLocation().Z - 88.0;
			if (bViewer || FVector::Dist2D(Ground, GetActorLocation()) > 900.0)
			{
				Ground = GetActorLocation() + GetActorForwardVector() * 300.0 - FVector(0, 0, 88.0);
			}
			FX->Spawn(AShowcaseFX::Cylinder, Ground, FRotator::ZeroRotator, FVector(0.3f, 0.3f, 0.02f), FVector(3.2f, 3.2f, 0.02f), Col, 0.9f, FVector::ZeroVector, 9.f, 0.7f, 0.f);
			FX->Spawn(AShowcaseFX::Cylinder, Ground, FRotator::ZeroRotator, FVector(0.2f, 0.2f, 0.4f), FVector(0.5f, 0.5f, 2.6f), Col, 0.5f, FVector::ZeroVector, 12.f, 0.5f, 0.f);
		}
		else
		{
			FX->Spawn(AShowcaseFX::Sphere, GetActorLocation(), FRotator::ZeroRotator, FVector(0.6f), FVector(2.6f), Col, 0.7f, FVector::ZeroVector, 5.f, 0.5f, 0.f);
		}
	}
	else if (Event == FName(TEXT("charge_released")))
	{
		const float L = Comp->GetChargeReleaseLevel();
		const float S = 0.14f + 0.36f * L;
		FX->Spawn(AShowcaseFX::Sphere, Muzzle, FRotator::ZeroRotator, FVector(S), FVector(S * 1.2f), Col, 0.8f, Dir * (1800.0 + 1600.0 * L), 12.f + 16.f * L, 0.9f, 0.3f);
	}
	else if (Event == FName(TEXT("deploy_release")) && !bViewer)
	{
		if (WorldBeacon)
		{
			WorldBeacon->Destroy();
		}
		const FTransform PropT = SkelMesh->GetSocketTransform(TEXT("prop_beacon"));
		AStaticMeshActor* A = GetWorld()->SpawnActor<AStaticMeshActor>(PropT.GetLocation(), PropT.Rotator());
		if (A)
		{
			UStaticMeshComponent* C = A->GetStaticMeshComponent();
			C->SetMobility(EComponentMobility::Movable);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			UStaticMesh* BeaconMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Operative/Props/SM_Beacon.SM_Beacon"));
			if (BeaconMesh)
			{
				C->SetStaticMesh(BeaconMesh);
				// the exported prop is modelled upright in its own frame: mesh +Z is the bone's long axis (Blender bone Y =
				// Unreal bone-local -Y), mesh X is the bone's X
				const FQuat PropFrame(FRotationMatrix::MakeFromXZ(FVector(1, 0, 0), FVector(0, -1, 0)));
				A->SetActorRotation(PropT.GetRotation() * PropFrame);
				const FVector Up = A->GetActorUpVector();
				UOperativeStateComponent::OnTrace.Broadcast(this, FString::Printf(TEXT("[0] BEACON world prop placed %.1f cm above the floor, up axis (%.2f %.2f %.2f)"),
					PropT.GetLocation().Z - GetMesh()->GetComponentLocation().Z, Up.X, Up.Y, Up.Z));
			}
			else
			{
				C->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")));
				A->SetActorScale3D(FVector(0.09f, 0.09f, 0.05f));
				if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Showcase/M_Solid.M_Solid")))
				{
					UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(M, A);
					Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.08f, 0.09f, 0.1f));
					Mid->SetVectorParameterValue(TEXT("Emissive"), Col * 3.f);
					C->SetMaterial(0, Mid);
				}
			}
			A->SetLifeSpan(8.f);
			WorldBeacon = A;
		}
		FX->Spawn(AShowcaseFX::Cylinder, PropT.GetLocation(), FRotator::ZeroRotator, FVector(0.1f, 0.1f, 0.01f), FVector(1.6f, 1.6f, 0.01f), Col, 0.8f, FVector::ZeroVector, 8.f, 0.6f, 0.f);
	}
	else if (Event == FName(TEXT("uplink_pulse")) || Event == FName(TEXT("uplink_begin")) || Event == FName(TEXT("charge_pulse")) || Event == FName(TEXT("channel_tick")))
	{
		const FVector Feet = GetActorLocation() - FVector(0, 0, 88.0);
		if (Event == FName(TEXT("uplink_pulse")) || Event == FName(TEXT("uplink_begin")))
		{
			FX->Spawn(AShowcaseFX::Cylinder, Feet, FRotator::ZeroRotator, FVector(0.3f, 0.3f, 0.01f), FVector(1.8f, 1.8f, 0.01f), Col, 1.1f, FVector::ZeroVector, 6.f, 0.55f, 0.f);
		}
	}
	else if (Event == FName(TEXT("uplink_complete")))
	{
		FX->Spawn(AShowcaseFX::Cylinder, GetActorLocation(), FRotator::ZeroRotator, FVector(0.9f, 0.9f, 0.1f), FVector(0.25f, 0.25f, 5.f), Col, 0.6f, FVector::ZeroVector, 12.f, 0.6f, 0.f);
	}
	else if (Event == FName(TEXT("blink_vanish")) || Event == FName(TEXT("blink_appear")))
	{
		FX->Spawn(AShowcaseFX::Cylinder, GetActorLocation(), FRotator::ZeroRotator, FVector(0.7f, 0.7f, 1.9f), FVector(0.05f, 0.05f, 2.6f), Col, 0.28f, FVector::ZeroVector, 14.f, 0.6f, 0.f);
	}
	else if (Event == FName(TEXT("land_impact")) || Event == FName(TEXT("ground_impact")))
	{
		const FVector Feet = GetActorLocation() - FVector(0, 0, 88.0);
		FX->Spawn(AShowcaseFX::Cylinder, Feet, FRotator::ZeroRotator, FVector(0.4f, 0.4f, 0.01f), FVector(1.5f, 1.5f, 0.01f), FLinearColor(0.7f, 0.7f, 0.7f), 0.35f, FVector::ZeroVector, 1.2f, 0.35f, 0.f);
	}
	else if (Event == FName(TEXT("line_start")))
	{
		PlayDialogueAudio(0.f);
	}
	else if (Event == FName(TEXT("respawn_materialize")))
	{
		FX->Spawn(AShowcaseFX::Cylinder, GetActorLocation() - FVector(0, 0, 86.0), FRotator::ZeroRotator, FVector(0.5f, 0.5f, 0.02f), FVector(1.7f, 1.7f, 0.02f), Col, 1.1f, FVector::ZeroVector, 7.f, 0.5f, 0.f);
		FX->Spawn(AShowcaseFX::Cylinder, GetActorLocation(), FRotator::ZeroRotator, FVector(0.06f, 0.06f, 5.f), FVector(0.5f, 0.5f, 1.9f), Col, 0.7f, FVector::ZeroVector, 6.f, 0.22f, 0.f);
	}
}

void AOperativeCharacter::UpdateEffects(float Dt)
{
	// material scalars
	HitFlash = FMath::Max(0.f, HitFlash - Dt * 5.f);
	const EOpState S = StateComp->GetState();
	if (S == EOpState::Action && StateComp->GetActionTag() == FName(TEXT("blink")) && StateComp->GetBaseClip().Id() == FName(TEXT("blink_out")))
	{
		const FOpClipPlay& P = StateComp->GetBaseClip();
		const float Vanish = P.Info->EventTime(TEXT("blink_vanish"), P.Duration());
		Dissolve = FMath::Clamp(P.Time / FMath::Max(Vanish, 0.01f), 0.f, 1.f);
		DissolveTarget = Dissolve;
	}
	else
	{
		Dissolve = FMath::FInterpConstantTo(Dissolve, DissolveTarget, Dt, DissolveSpeed);
	}
	for (UMaterialInstanceDynamic* Mid : SlotMids)
	{
		if (Mid && DisplayMode == EOpDisplayMode::Textured)
		{
			Mid->SetScalarParameterValue(TEXT("HitFlash"), HitFlash);
			Mid->SetScalarParameterValue(TEXT("Dissolve"), Dissolve);
		}
	}
	AShowcaseFX* FX = AShowcaseFX::Get(GetWorld());
	if (!FX)
	{
		return;
	}
	USkeletalMeshComponent* SkelMesh = GetMesh();
	const FLinearColor Col = GetTeamColor();
	const FName BeamKey(*FString::Printf(TEXT("beam_%d"), InstanceIndex));
	const FName ChargeKey(*FString::Printf(TEXT("charge_%d"), InstanceIndex));
	const FVector Muzzle = SkelMesh->GetSocketLocation(TEXT("emitter_muzzle"));
	if (StateComp->IsChanneling() && S == EOpState::Action)
	{
		FVector Target = StateComp->Input.bHasAimPoint ? StateComp->Input.AimPoint : Muzzle + GetActorForwardVector() * 700.0;
		if (FVector::Dist(Target, Muzzle) > 1200.0)
		{
			Target = Muzzle + (Target - Muzzle).GetSafeNormal() * 1200.0;
		}
		FX->SetBeam(BeamKey, Muzzle, Target, 2.2f + 0.5f * FMath::Sin((float)StateComp->GetStateTime() * 30.f), Col, 16.f);
	}
	else
	{
		FX->ClearPersistent(BeamKey);
	}
	const float Charge = StateComp->GetChargeLevel();
	if (Charge > 0.f)
	{
		const float Sc = 0.05f + 0.22f * Charge;
		FX->SetPersistent(ChargeKey, AShowcaseFX::Sphere, FTransform(FQuat::Identity, Muzzle, FVector(Sc)), Col, 6.f + 18.f * Charge, 0.75f);
	}
	else
	{
		FX->ClearPersistent(ChargeKey);
	}
	// melee hit window: emissive volume along the blade
	const bool bWindow = StateComp->IsHitWindowOpen() && S == EOpState::Action;
	if (bWindow)
	{
		const FVector A = SkelMesh->GetSocketLocation(TEXT("blade_base"));
		const FVector B = SkelMesh->GetSocketLocation(TEXT("blade_tip"));
		const FVector D = B - A;
		const double Len = FMath::Max(D.Size(), 1.0);
		BladeGlow->SetWorldTransform(FTransform(FRotationMatrix::MakeFromX(D / Len).ToQuat(), A + D * 0.5, FVector(Len / 100.0 * 1.25, 0.02, 0.07)));
	}
	if (BladeGlow->IsVisible() != bWindow)
	{
		BladeGlow->SetVisibility(bWindow);
	}
}

// ------------------------------------------------------------------------------------------------ autopilot (extra instances)
void AOperativeCharacter::TickAutopilot(float Dt)
{
	// deterministic loop: strafe on a circle around a point while aiming at it, with a fixed action schedule
	AutoTime += Dt;
	const float Period = 16.f;
	const float T = FMath::Fmod(AutoTime + InstanceIndex * 1.37f, Period);
	const int32 Cycle = FMath::FloorToInt((AutoTime + InstanceIndex * 1.37f) / Period);
	FOpInput& In = StateComp->Input;
	In = FOpInput();
	const FVector Center = AutopilotCenter;
	FVector To = Center - GetActorLocation();
	To.Z = 0.0;
	const double Dist = To.Size();
	const FVector Radial = To.GetSafeNormal();
	const FVector Tangent = FVector::CrossProduct(FVector::UpVector, Radial) * ((InstanceIndex % 2) ? 1.0 : -1.0);
	In.bHasAimPoint = true;
	In.AimPoint = Center + FVector(0, 0, 120.0 + 60.0 * FMath::Sin(AutoTime * 0.7f + InstanceIndex));
	const double Want = 260.0 + 45.0 * (InstanceIndex % 3);
	FVector Move = Tangent + Radial * FMath::Clamp((Dist - Want) / 120.0, -1.0, 1.0);
	In.bAim = T > 2.f && T < 9.f;
	In.bWalk = (InstanceIndex % 3) == 0;
	if (T < 11.5f)
	{
		In.MoveDir = Move.GetSafeNormal();
	}
	struct FStep { float Time; int32 Kind; };
	static const FStep Steps[] = { { 2.5f, 0 }, { 3.6f, 1 }, { 5.0f, 2 }, { 6.4f, 3 }, { 7.6f, 0 }, { 9.2f, 4 }, { 10.4f, 5 }, { 11.8f, 6 }, { 13.6f, 7 }, { 14.4f, 8 } };
	const int32 NumSteps = UE_ARRAY_COUNT(Steps);
	const int32 Key = Cycle * 100;
	for (int32 i = 0; i < NumSteps; ++i)
	{
		if (T >= Steps[i].Time && AutoStep < Key + i)
		{
			AutoStep = Key + i;
			switch ((Steps[i].Kind + InstanceIndex) % 9)
			{
			case 0: StateComp->DoRanged(false); break;
			case 1: StateComp->DoRanged(true); break;
			case 2: StateComp->DoCast(TEXT("directional")); break;
			case 3: StateComp->ApplyHit(90.f * (InstanceIndex % 4), false); break;
			case 4: StateComp->DoJump(); break;
			case 5: StateComp->DoDash(90.f * (InstanceIndex % 4)); break;
			case 6: StateComp->DoMelee(); break;
			case 7: StateComp->DoCast(TEXT("self")); break;
			case 8: StateComp->DoReload(); break;
			}
		}
	}
}

void AOperativeCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (bAutopilot && StateComp->IsAlive())
	{
		TickAutopilot(DeltaTime);
	}
	UpdateEffects(DeltaTime);
}
