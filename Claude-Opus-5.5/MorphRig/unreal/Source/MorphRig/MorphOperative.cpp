#include "MorphOperative.h"

#include "Animation/AnimSequence.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/KismetMathLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "MorphAnimInstance.h"
#include "Sound/SoundWave.h"

DEFINE_LOG_CATEGORY_STATIC(LogMorph, Log, All);

namespace
{
	constexpr float WalkSpeed = 150.f;
	constexpr float RunSpeed = 400.f;
	constexpr float SprintSpeed = 650.f;
	const TCHAR* DirSuffix[8] = {TEXT("f"), TEXT("fl"), TEXT("l"), TEXT("bl"), TEXT("b"), TEXT("br"), TEXT("r"), TEXT("fr")};
	const float DirAngle[8] = {0.f, 45.f, 90.f, 135.f, 180.f, -135.f, -90.f, -45.f};

	FName N(const TCHAR* S) { return FName(S); }
	FName N(const FString& S) { return FName(*S); }
}

bool FMorphSlot::Finished() const
{
	if (!Clip || bLoco || Clip->bLoop)
	{
		return false;
	}
	return Time >= Clip->Duration - 1e-4f;
}

// =====================================================================================================
AMorphOperative::AMorphOperative()
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(32.f, 90.f);
	USkeletalMeshComponent* M = GetMesh();
	M->SetRelativeLocation(FVector(0.f, 0.f, -90.f));
	M->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));   // mesh faces +Y, actor forward is +X
	M->SetAnimInstanceClass(UMorphAnimInstance::StaticClass());
	M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	UCharacterMovementComponent* CM = GetCharacterMovement();
	CM->MaxWalkSpeed = RunSpeed;
	CM->MaxAcceleration = 1400.f;
	CM->BrakingDecelerationWalking = 1600.f;
	CM->GroundFriction = 8.f;
	CM->JumpZVelocity = 480.f;
	CM->AirControl = 0.35f;
	CM->bOrientRotationToMovement = false;
	CM->MaxStepHeight = 25.f;
	CM->SetWalkableFloorAngle(30.f);
	bUseControllerRotationYaw = false;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 380.f;
	CameraBoom->SetRelativeRotation(FRotator(-15.f, 0.f, 0.f));
	CameraBoom->bDoCollisionTest = false;
	CameraBoom->bUsePawnControlRotation = false;
	CameraBoom->bInheritYaw = true;      // the controller sets the boom's world rotation (with false the arm would read relative yaw as world yaw)
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom);
	Camera->SetFieldOfView(55.f);

	Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Voice"));
	Voice->SetupAttachment(M, TEXT("head"));
	Voice->bAutoActivate = false;

	FxSphere = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Fx"));
	FxSphere->SetupAttachment(RootComponent);
	FxSphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	FxSphere->SetCastShadow(false);
	FxSphere->SetVisibility(false);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (Sphere.Succeeded())
	{
		FxSphere->SetStaticMesh(Sphere.Object);
	}
	static ConstructorHelpers::FObjectFinder<USkeletalMesh> Mesh(TEXT("/Game/MorphRig/Character/SK_Operative.SK_Operative"));
	if (Mesh.Succeeded())
	{
		M->SetSkeletalMeshAsset(Mesh.Object);
	}
	static ConstructorHelpers::FObjectFinder<USoundWave> Line(TEXT("/Game/MorphRig/Audio/SW_Dialogue.SW_Dialogue"));
	if (Line.Succeeded())
	{
		Voice->SetSound(Line.Object);
	}
}

void AMorphOperative::BeginPlay()
{
	Super::BeginPlay();
	USkeletalMeshComponent* M = GetMesh();
	MIDs.Reset();
	for (int32 i = 0; i < M->GetNumMaterials(); ++i)
	{
		MIDs.Add(M->CreateDynamicMaterialInstance(i));
	}
	if (UMaterialInterface* FxMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/MorphRig/Materials/M_Fx.M_Fx")))
	{
		FxSphere->SetMaterial(0, UMaterialInstanceDynamic::Create(FxMat, this));
	}
	SetTeam(Team);
	PlayLocomotion(0.f);
	Trace(TEXT("spawned"));
}

// ===================================================================================== commands
void AMorphOperative::SetMoveInput(const FVector2D& InWorldDir, float InSpeedScale)
{
	MoveInput = InWorldDir.GetSafeNormal() * FMath::Min(InWorldDir.Size(), 1.f);
	SpeedScale = FMath::Clamp(InSpeedScale, 0.f, 1.f);
}

void AMorphOperative::SetAimInput(bool bInAiming, const FVector& WorldTarget)
{
	bAiming = bInAiming;
	AimTarget = WorldTarget;
}

int32 AMorphOperative::Priority(EMorphState S)
{
	switch (S)
	{
	case EMorphState::Locomotion: return 0;
	case EMorphState::Transition: return 5;
	case EMorphState::Airborne: return 10;
	case EMorphState::Emote: return 12;
	case EMorphState::Dialogue: return 12;
	case EMorphState::Preview: return 14;
	case EMorphState::Action: return 20;
	case EMorphState::Channel: return 20;
	case EMorphState::Charge: return 20;
	case EMorphState::Uplink: return 20;
	case EMorphState::Dash: return 25;
	case EMorphState::Blink: return 25;
	case EMorphState::Knockback: return 40;
	case EMorphState::Stun: return 50;
	case EMorphState::Sleep: return 50;
	case EMorphState::Knockup: return 60;
	case EMorphState::Down: return 60;
	case EMorphState::Respawn: return 90;
	case EMorphState::Dead: return 100;
	}
	return 0;
}

bool AMorphOperative::CanEnter(EMorphState S) const
{
	if (State == EMorphState::Dead)
	{
		return S == EMorphState::Respawn;
	}
	if (S == EMorphState::Respawn)
	{
		return false;
	}
	if (State == EMorphState::Respawn)
	{
		return S == EMorphState::Dead;
	}
	// voluntary actions need the ground
	if (GetCharacterMovement()->IsFalling() && Priority(S) < Priority(EMorphState::Knockback) &&
	    S != EMorphState::Airborne && S != EMorphState::Dash && S != EMorphState::Blink)
	{
		return false;
	}
	return Priority(S) >= Priority(State) || State == EMorphState::Locomotion || State == EMorphState::Transition ||
	       State == EMorphState::Emote || State == EMorphState::Preview || State == EMorphState::Dialogue;
}

void AMorphOperative::EnterState(EMorphState S, FName Clip, float Blend)
{
	const EMorphState Old = State;
	// leaving sustained states: stop their side effects
	if (Old == EMorphState::Dialogue && Voice->IsPlaying())
	{
		Voice->Stop();
	}
	State = S;
	StateTime = 0.f;
	Phase = 0;
	bComboQueued = false;
	if (S != EMorphState::Locomotion)
	{
		StopUpper(0.15f);
	}
	if (!Clip.IsNone())
	{
		PlayFull(Clip, Blend);
	}
	else if (S == EMorphState::Locomotion)
	{
		PlayLocomotion(Blend);
	}
	Trace(FString::Printf(TEXT("state %s -> %s clip=%s"), *UEnum::GetValueAsString(Old), *StateName(),
	                      *MorphIdStr(Clip)));
}

void AMorphOperative::CmdJump()
{
	if (!CanEnter(EMorphState::Airborne) || GetCharacterMovement()->IsFalling())
	{
		return;
	}
	EnterState(EMorphState::Airborne, N(TEXT("jump_start")), 0.1f);
}

FName AMorphOperative::DirClip(const TCHAR* Prefix) const
{
	float A = MoveInput.IsNearlyZero() ? 0.f : LocalMoveAngle();
	const TCHAR* Dir = TEXT("f");
	if (A > 45.f && A <= 135.f) Dir = TEXT("l");
	else if (A < -45.f && A >= -135.f) Dir = TEXT("r");
	else if (FMath::Abs(A) > 135.f) Dir = TEXT("b");
	return N(FString::Printf(TEXT("%s_%s"), Prefix, Dir));
}

void AMorphOperative::CmdDash()
{
	if (!CanEnter(EMorphState::Dash) || GetCharacterMovement()->IsFalling())
	{
		return;
	}
	EnterState(EMorphState::Dash, DirClip(TEXT("dash")), 0.08f);
}

void AMorphOperative::CmdBlink()
{
	if (!CanEnter(EMorphState::Blink))
	{
		return;
	}
	EnterState(EMorphState::Blink, N(TEXT("blink_out")), 0.1f);
}

void AMorphOperative::CmdMelee()
{
	if (State == EMorphState::Action && (PrimaryId() == N(TEXT("melee_1")) || PrimaryId() == N(TEXT("melee_2"))))
	{
		bComboQueued = true;
		return;
	}
	if (!CanEnter(EMorphState::Action))
	{
		return;
	}
	EnterState(EMorphState::Action, N(TEXT("melee_1")), 0.1f);
}

void AMorphOperative::CmdFire(bool bBurst)
{
	if (State != EMorphState::Locomotion && State != EMorphState::Transition)
	{
		return;
	}
	bAiming = true;
	PlayUpper(bBurst ? N(TEXT("ranged_burst")) : N(TEXT("ranged_fire")));
}

void AMorphOperative::CmdReload()
{
	if (State != EMorphState::Locomotion && State != EMorphState::Transition)
	{
		return;
	}
	PlayUpper(N(TEXT("reload")));
}

void AMorphOperative::CmdCast(int32 Kind)
{
	if (Kind == 0 && (State == EMorphState::Locomotion || State == EMorphState::Transition) && GetSpeedCms() > 30.f)
	{
		PlayUpper(N(TEXT("cast_directional")));      // moving: upper-body layer
		return;
	}
	if (!CanEnter(EMorphState::Action))
	{
		return;
	}
	static const TCHAR* Names[3] = {TEXT("cast_directional"), TEXT("cast_ground"), TEXT("cast_self")};
	EnterState(EMorphState::Action, N(Names[FMath::Clamp(Kind, 0, 2)]), 0.12f);
}

void AMorphOperative::CmdChannel(bool bPressed)
{
	if (bPressed)
	{
		if (State == EMorphState::Channel || !CanEnter(EMorphState::Channel))
		{
			return;
		}
		bHeld = true;
		EnterState(EMorphState::Channel, N(TEXT("channel_start")), 0.15f);
	}
	else if (State == EMorphState::Channel && bHeld)
	{
		bHeld = false;
		if (Phase <= 1)
		{
			Phase = 2;
			PlayFull(N(TEXT("channel_end")), 0.15f);
			Trace(TEXT("channel released"));
		}
	}
}

void AMorphOperative::CmdChannelInterrupt()
{
	if (State == EMorphState::Channel && Phase <= 1)
	{
		bHeld = false;
		Phase = 3;
		PlayFull(N(TEXT("channel_interrupt")), 0.08f);
		Trace(TEXT("channel interrupted"));
	}
}

void AMorphOperative::CmdCharge(bool bPressed)
{
	if (bPressed)
	{
		if (State == EMorphState::Charge || !CanEnter(EMorphState::Charge))
		{
			return;
		}
		bHeld = true;
		EnterState(EMorphState::Charge, N(TEXT("charge_start")), 0.12f);
	}
	else if (State == EMorphState::Charge && bHeld && Phase <= 1)
	{
		bHeld = false;
		Phase = 2;
		PlayFull(N(TEXT("charge_release")), 0.08f);
		Trace(FString::Printf(TEXT("charge released after %.2fs"), StateTime));
	}
}

void AMorphOperative::CmdChargeCancel()
{
	if (State == EMorphState::Charge && Phase <= 1)
	{
		bHeld = false;
		Phase = 3;
		PlayFull(N(TEXT("charge_cancel")), 0.1f);
		Trace(TEXT("charge cancelled"));
	}
}

void AMorphOperative::CmdDeploy()
{
	if (!CanEnter(EMorphState::Action) || bBeaconHidden)
	{
		return;
	}
	EnterState(EMorphState::Action, N(TEXT("deploy")), 0.15f);
}

void AMorphOperative::CmdUplink(bool bPressed)
{
	if (bPressed)
	{
		if (State == EMorphState::Uplink || !CanEnter(EMorphState::Uplink))
		{
			return;
		}
		bHeld = true;
		EnterState(EMorphState::Uplink, N(TEXT("uplink_start")), 0.15f);
	}
	else if (State == EMorphState::Uplink && bHeld && Phase <= 1)
	{
		bHeld = false;
		Phase = 3;
		PlayFull(N(TEXT("uplink_cancel")), 0.1f);
		Trace(TEXT("uplink cancelled (released early)"));
	}
}

void AMorphOperative::CmdHit(int32 Dir)
{
	if (State == EMorphState::Dead || State == EMorphState::Down || State == EMorphState::Respawn)
	{
		return;
	}
	static const TCHAR* Names[4] = {TEXT("hit_f"), TEXT("hit_b"), TEXT("hit_l"), TEXT("hit_r")};
	const int32 D = Dir >= 0 ? Dir : (HitCycle++ % 4);
	PlayAdditive(N(Names[D]), 1.f);
	bFromFront = (D != 1);
	Trace(FString::Printf(TEXT("hit %s (additive)"), Names[D]));
	// documented rule: hits interrupt channel and uplink, charge keeps its stored energy
	if (State == EMorphState::Channel)
	{
		CmdChannelInterrupt();
	}
	else if (State == EMorphState::Uplink && Phase <= 1)
	{
		bHeld = false;
		Phase = 3;
		PlayFull(N(TEXT("uplink_cancel")), 0.1f);
	}
}

void AMorphOperative::CmdStun()
{
	if (!CanEnter(EMorphState::Stun))
	{
		return;
	}
	EnterState(EMorphState::Stun, N(TEXT("stun_start")), 0.1f);
}

void AMorphOperative::CmdKnockback()
{
	if (!CanEnter(EMorphState::Knockback))
	{
		return;
	}
	EnterState(EMorphState::Knockback, N(TEXT("knockback")), 0.06f);
	LaunchCharacter(-GetActorForwardVector() * 520.f + FVector(0, 0, 60.f), true, true);   // host-driven travel
}

void AMorphOperative::CmdKnockup()
{
	if (!CanEnter(EMorphState::Knockup))
	{
		return;
	}
	EnterState(EMorphState::Knockup, N(TEXT("knockup_start")), 0.06f);
}

void AMorphOperative::CmdKnockdown(bool bInFront)
{
	if (!CanEnter(EMorphState::Down))
	{
		return;
	}
	// a hit from the front throws the body backward (face up), from behind face down
	bFromFront = bInFront;
	EnterState(EMorphState::Down, bInFront ? N(TEXT("knockdown_back")) : N(TEXT("knockdown_front")), 0.08f);
}

void AMorphOperative::CmdSleep()
{
	if (State == EMorphState::Sleep && Phase == 1)
	{
		Phase = 2;
		PlayFull(N(TEXT("sleep_end")), 0.2f);
		return;
	}
	if (!CanEnter(EMorphState::Sleep))
	{
		return;
	}
	EnterState(EMorphState::Sleep, N(TEXT("sleep_start")), 0.25f);
}

void AMorphOperative::CmdDeath(bool bInFront)
{
	if (bDeadOnce || State == EMorphState::Dead)
	{
		return;                           // death happens once until respawn
	}
	bDeadOnce = true;
	bHeld = false;
	bFromFront = bInFront;
	Additive.Reset();
	GetCharacterMovement()->StopMovementImmediately();
	EnterState(EMorphState::Dead, bInFront ? N(TEXT("death_front")) : N(TEXT("death_back")), 0.08f);
}

void AMorphOperative::CmdRespawn()
{
	if (State != EMorphState::Dead)
	{
		return;
	}
	ClearProps();
	State = EMorphState::Respawn;   // allowed transition (Dead -> Respawn)
	StateTime = 0.f;
	Phase = 0;
	PlayFull(N(TEXT("respawn")), 0.2f);
	Trace(TEXT("state Dead -> Respawn clip=respawn"));
}

void AMorphOperative::CmdEmote(FName Clip)
{
	if (!CanEnter(EMorphState::Emote))
	{
		return;
	}
	EnterState(EMorphState::Emote, Clip, 0.2f);
}

void AMorphOperative::CmdDialogue()
{
	if (!CanEnter(EMorphState::Dialogue))
	{
		return;
	}
	GetCharacterMovement()->StopMovementImmediately();
	EnterState(EMorphState::Dialogue, N(TEXT("dialogue")), 0.25f);
	if (Voice->Sound)
	{
		Voice->Play(0.f);
	}
}

void AMorphOperative::CmdPreview(FName Clip, bool bLoopPreview)
{
	if (!Library || !Library->Find(Clip))
	{
		return;
	}
	if (State == EMorphState::Dead)
	{
		bDeadOnce = false;
	}
	bPreviewLoop = bLoopPreview;
	Additive.Reset();
	const FMorphClip* C = Library->Find(Clip);
	if (C->bAdditive)
	{
		PlayAdditive(Clip, 1.f);
		Trace(FString::Printf(TEXT("preview additive %s"), *MorphIdStr(Clip)));
		return;
	}
	if (C->Layer == TEXT("upper_body") && State == EMorphState::Locomotion)
	{
		PlayUpper(Clip);
		return;
	}
	State = EMorphState::Preview;
	StateTime = 0.f;
	PlayFull(Clip, 0.2f, 1.f, true);
	if (Clip == N(TEXT("dialogue")) && Voice->Sound)
	{
		Voice->Play(0.f);
	}
	Trace(FString::Printf(TEXT("preview %s"), *MorphIdStr(Clip)));
}

void AMorphOperative::CmdResume()
{
	if (State == EMorphState::Preview || State == EMorphState::Emote || State == EMorphState::Dialogue)
	{
		EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
	}
}

void AMorphOperative::CmdResetCharacter()
{
	ClearProps();
	bDeadOnce = false;
	bHeld = false;
	Additive.Reset();
	Upper.Reset();
	UpperAlpha = UpperTarget = 0.f;
	GetCharacterMovement()->StopMovementImmediately();
	State = EMorphState::Locomotion;
	PlayLocomotion(0.1f);
	ClearFace();
	Trace(TEXT("reset"));
}

// ===================================================================================== slots
void AMorphOperative::PlayFull(FName Id, float Blend, float Rate, bool bHold)
{
	const FMorphClip* C = Library ? Library->Find(Id) : nullptr;
	if (!C)
	{
		UE_LOG(LogMorph, Warning, TEXT("clip %s not found"), *Id.ToString());
		return;
	}
	const float Speed = Blend > 1e-3f ? 1.f / Blend : 1000.f;
	for (FMorphSlot& S : Base)
	{
		S.Target = 0.f;
		S.FadeSpeed = Speed;
		S.bEvents = false;
	}
	FMorphSlot S;
	S.Clip = C;
	S.Rate = Rate;
	S.Weight = Base.Num() ? 0.f : 1.f;
	S.Target = 1.f;
	S.FadeSpeed = Speed;
	S.bHoldEnd = bHold || C->Form == TEXT("pose");
	Base.Add(S);
	if (C->Id == N(TEXT("dialogue")) || C->Id == N(TEXT("demo_deformation")))
	{
		S.bHoldEnd = true;
	}
}

void AMorphOperative::PlayLocomotion(float Blend)
{
	const float Speed = Blend > 1e-3f ? 1.f / Blend : 1000.f;
	for (FMorphSlot& S : Base)
	{
		S.Target = 0.f;
		S.FadeSpeed = Speed;
		S.bEvents = false;
	}
	FMorphSlot S;
	S.bLoco = true;
	S.Weight = Base.Num() ? 0.f : 1.f;
	S.Target = 1.f;
	S.FadeSpeed = Speed;
	Base.Add(S);
}

void AMorphOperative::PlayUpper(FName Id, float Blend)
{
	const FMorphClip* C = Library ? Library->Find(Id) : nullptr;
	if (!C)
	{
		return;
	}
	for (FMorphSlot& S : Upper)
	{
		S.Target = 0.f;
		S.FadeSpeed = 1.f / FMath::Max(Blend, 0.01f);
		S.bEvents = false;
	}
	FMorphSlot S;
	S.Clip = C;
	S.Weight = Upper.Num() ? 0.f : 1.f;
	S.Target = 1.f;
	S.FadeSpeed = 1.f / FMath::Max(Blend, 0.01f);
	Upper.Add(S);
	UpperTarget = 1.f;
	Trace(FString::Printf(TEXT("upper-body %s"), *Id.ToString()));
}

void AMorphOperative::StopUpper(float Blend)
{
	UpperTarget = 0.f;
	for (FMorphSlot& S : Upper)
	{
		S.bEvents = false;
	}
}

void AMorphOperative::PlayAdditive(FName Id, float Weight)
{
	const FMorphClip* C = Library ? Library->Find(Id) : nullptr;
	if (!C)
	{
		return;
	}
	FMorphSlot S;
	S.Clip = C;
	S.Weight = Weight;
	S.Target = Weight;
	S.FadeSpeed = 12.f;
	Additive.Add(S);
}

FMorphSlot* AMorphOperative::Primary()
{
	for (int32 i = Base.Num() - 1; i >= 0; --i)
	{
		if (Base[i].Target > 0.f)
		{
			return &Base[i];
		}
	}
	return Base.Num() ? &Base.Last() : nullptr;
}

const FMorphSlot* AMorphOperative::Primary() const
{
	return const_cast<AMorphOperative*>(this)->Primary();
}

FName AMorphOperative::PrimaryId() const
{
	const FMorphSlot* P = Primary();
	return (P && P->Clip) ? P->Clip->Id : (P && P->bLoco ? N(TEXT("locomotion")) : NAME_None);
}

bool AMorphOperative::PrimaryDone(float Margin) const
{
	const FMorphSlot* P = Primary();
	if (!P || !P->Clip || P->bLoco)
	{
		return false;
	}
	if (P->Clip->bLoop)
	{
		return false;
	}
	return P->Time >= P->Clip->Duration - Margin - 1e-4f;
}

void AMorphOperative::TickSlots(TArray<FMorphSlot>& Slots, float Dt, bool bFire)
{
	for (FMorphSlot& S : Slots)
	{
		S.Weight = FMath::FInterpConstantTo(S.Weight, S.Target, Dt, S.FadeSpeed);
		if (S.bLoco || !S.Clip)
		{
			continue;
		}
		const float Len = S.Clip->Duration;
		S.PrevTime = S.Time;
		float T = S.Time + Dt * S.Rate * RateScale;
		if (S.Clip->bLoop && Len > 1e-4f)
		{
			if (T >= Len)
			{
				if (bFire && S.bEvents)
				{
					FireMarkers(S, S.PrevTime, Len + 1e-4f);
				}
				T = FMath::Fmod(T, Len);
				if (bFire && S.bEvents)
				{
					FireMarkers(S, -1e-4f, T);
				}
				S.Time = T;
				continue;
			}
		}
		else
		{
			T = FMath::Min(T, Len);
		}
		if (bFire && S.bEvents && T > S.PrevTime)
		{
			FireMarkers(S, S.PrevTime, T);
		}
		S.Time = T;
	}
	Slots.RemoveAll([](const FMorphSlot& S) { return S.Target <= 0.f && S.Weight <= 1e-4f; });
}

void AMorphOperative::FireMarkers(const FMorphSlot& S, float From, float To)
{
	for (const FMorphMarker& M : S.Clip->Markers)
	{
		if (M.Time > From && M.Time <= To)
		{
			OnEvent(S.Clip->Id, M.Name);
		}
	}
}

// ===================================================================================== tick
void AMorphOperative::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Library)
	{
		return;
	}
	TickController(DeltaSeconds);
	if (FxLife > 0.f)
	{
		FxLife -= DeltaSeconds;
		if (FxLife <= 0.f)
		{
			FxSphere->SetVisibility(false);
		}
	}
}

void AMorphOperative::TickController(float Dt)
{
	StateTime += Dt;
	if (bAutoPilot)
	{
		AutoTimer -= Dt;
		if (AutoTimer <= 0.f)
		{
			AutoTimer = Rng.FRandRange(2.5f, 5.f);
			const int32 R = Rng.RandRange(0, 11);
			const float A = Rng.FRandRange(-PI, PI);
			SetMoveInput(FVector2D(FMath::Cos(A), FMath::Sin(A)), R < 6 ? Rng.FRandRange(0.35f, 1.f) : 0.f);
			SetSprint(R == 1);
			if (R == 6) CmdMelee();
			else if (R == 7) CmdFire(Rng.RandBool());
			else if (R == 8) CmdCast(Rng.RandRange(0, 2));
			else if (R == 9) CmdJump();
			else if (R == 10) CmdHit();
			else if (R == 11) CmdDash();
		}
		// keep instances near home
		const FVector Home = GetActorLocation();
		if (Home.Size2D() > 3000.f)
		{
			SetMoveInput(FVector2D(-Home.X, -Home.Y).GetSafeNormal(), 0.5f);
		}
	}
	TickState(Dt);
	TickLocomotion(Dt);
	// the primary slot fires events; fading slots do not (no duplicates on blend / interruption)
	TickSlots(Base, Dt, true);
	UpperAlpha = FMath::FInterpConstantTo(UpperAlpha, UpperTarget, Dt, 6.f);
	TickSlots(Upper, Dt, true);
	for (FMorphSlot& S : Upper)
	{
		if (S.Target > 0.f && S.Finished())
		{
			UpperTarget = 0.f;
			S.Target = 0.f;
			S.FadeSpeed = 5.f;
			S.bEvents = false;
		}
	}
	if (UpperAlpha <= 0.f && UpperTarget <= 0.f)
	{
		Upper.Reset();
	}
	// additive hits fade out at their end
	for (FMorphSlot& S : Additive)
	{
		if (S.Finished())
		{
			S.Target = 0.f;
		}
	}
	TickSlots(Additive, Dt, true);
	TickRootMotion(Dt);
	TickFootIK(Dt);
	TickLookAt(Dt);
	BuildRequest();
}

float AMorphOperative::LocalMoveAngle() const
{
	const FVector V = GetVelocity().Size2D() > 20.f ? GetVelocity() : FVector(MoveInput.X, MoveInput.Y, 0.f);
	if (V.IsNearlyZero())
	{
		return 0.f;
	}
	const FVector L = GetActorTransform().InverseTransformVectorNoScale(V);
	// actor space: +X forward, +Y right -> angle positive to the left
	return FMath::RadiansToDegrees(FMath::Atan2(-L.Y, L.X));
}

FName AMorphOperative::IdleClip() const
{
	switch (Stance)
	{
	case EMorphStance::Combat: return N(TEXT("idle_combat"));
	case EMorphStance::Wounded: return N(TEXT("idle_wounded"));
	default: return N(TEXT("idle_relaxed"));
	}
}

void AMorphOperative::TickLocomotion(float Dt)
{
	UCharacterMovementComponent* CM = GetCharacterMovement();
	const bool bMoveAllowed = State == EMorphState::Locomotion || State == EMorphState::Transition ||
	                          State == EMorphState::Airborne;
	// desired speed: walk / run / sprint (sprint only while moving forward)
	float Desired = SpeedScale * (bSprint ? SprintSpeed : RunSpeed);
	if (Stance == EMorphStance::Wounded)
	{
		Desired = FMath::Min(Desired, WalkSpeed);
	}
	CM->MaxWalkSpeed = FMath::Max(Desired, 10.f);
	if (bMoveAllowed && !MoveInput.IsNearlyZero())
	{
		AddMovementInput(FVector(MoveInput.X, MoveInput.Y, 0.f), 1.f);
	}
	// facing: strafe/aim keeps the facing on the aim target, otherwise turn toward movement
	float DesiredYaw = GetActorRotation().Yaw;
	if ((bStrafe || bAiming) && !AimTarget.IsNearlyZero())
	{
		const FVector To = AimTarget - GetActorLocation();
		if (To.Size2D() > 50.f)
		{
			DesiredYaw = To.Rotation().Yaw;
		}
	}
	else if (!MoveInput.IsNearlyZero())
	{
		DesiredYaw = FVector(MoveInput.X, MoveInput.Y, 0.f).Rotation().Yaw;
	}
	const bool bCanTurnActor = State == EMorphState::Locomotion || State == EMorphState::Airborne ||
	                           (State == EMorphState::Action && StateTime < 0.1f);
	const float Speed = GetSpeedCms();
	// idle turn in place with a clip (turn_l90 / turn_r90) instead of sliding the feet
	const float DeltaYaw = FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw, DesiredYaw);
	if (State == EMorphState::Locomotion && Speed < 15.f && MoveInput.IsNearlyZero() && FMath::Abs(DeltaYaw) > 60.f &&
	    (bStrafe || bAiming))
	{
		PendingYaw = DeltaYaw > 0.f ? 90.f : -90.f;
		EnterState(EMorphState::Transition, DeltaYaw > 0.f ? N(TEXT("turn_r90")) : N(TEXT("turn_l90")), 0.15f);
		Phase = 10;   // turn
	}
	else if (bCanTurnActor && (Speed > 15.f || FMath::Abs(DeltaYaw) < 60.f || !(bStrafe || bAiming)))
	{
		FRotator R = GetActorRotation();
		R.Yaw = FMath::FixedTurn(R.Yaw, DesiredYaw, 540.f * Dt);
		SetActorRotation(R);
	}
	// start / stop / pivot transitions (forward travel)
	const float MoveAngle = LocalMoveAngle();
	if (State == EMorphState::Locomotion && !CM->IsFalling())
	{
		const bool bWantMove = !MoveInput.IsNearlyZero() && SpeedScale > 0.2f;
		if (bWantMove && PrevSpeed < 10.f && FMath::Abs(MoveAngle) < 25.f && LocoIdle > 0.9f)
		{
			EnterState(EMorphState::Transition, N(TEXT("start_f")), 0.12f);
			Phase = 20;
		}
		else if (!bWantMove && PrevSpeed > 110.f && PrevSpeed < 220.f && FMath::Abs(LastMoveAngle) < 25.f)
		{
			EnterState(EMorphState::Transition, N(TEXT("stop_f")), 0.12f);
			Phase = 21;
		}
		else if (bWantMove && Speed > 120.f && !(bStrafe || bAiming))
		{
			const FVector Want(MoveInput.X, MoveInput.Y, 0.f);
			const float Rev = FMath::FindDeltaAngleDegrees(GetVelocity().Rotation().Yaw, Want.Rotation().Yaw);
			if (FMath::Abs(Rev) > 140.f)
			{
				PendingYaw = 180.f;
				EnterState(EMorphState::Transition, Rev > 0.f ? N(TEXT("pivot_r180")) : N(TEXT("pivot_l180")), 0.1f);
				Phase = 22;
			}
		}
	}
	if (Speed > 20.f)
	{
		LastMoveAngle = MoveAngle;
	}
	PrevSpeed = Speed;
	// blend parameters with smoothing
	const float WR = FMath::Clamp((Speed - WalkSpeed) / (RunSpeed - WalkSpeed), 0.f, 1.f);
	LocoWalkRun = FMath::FInterpTo(LocoWalkRun, WR, Dt, 8.f);
	const bool bFwd = FMath::Abs(MoveAngle) < 30.f;
	const float SP = (bSprint && bFwd) ? FMath::Clamp((Speed - RunSpeed) / (SprintSpeed - RunSpeed), 0.f, 1.f) : 0.f;
	LocoSprint = FMath::FInterpTo(LocoSprint, SP, Dt, 6.f);
	LocoIdle = FMath::FInterpTo(LocoIdle, Speed < 12.f ? 1.f : 0.f, Dt, 9.f);
	// synced cycle phase: frequency follows the controller velocity (playback adapts to speed)
	auto Dur = [this](const TCHAR* Id) {
		const FMorphClip* C = Library->Find(N(Id));
		return C ? FMath::Max(C->Duration, 0.1f) : 1.f;
	};
	const float Walk = 1.f - LocoWalkRun;
	const float Run = LocoWalkRun * (1.f - LocoSprint);
	const float Spr = LocoWalkRun * LocoSprint;
	const float Freq = Walk * (FMath::Clamp(Speed / WalkSpeed, 0.35f, 1.6f) / Dur(TEXT("walk_f"))) +
	                   Run * (FMath::Clamp(Speed / RunSpeed, 0.5f, 1.4f) / Dur(TEXT("run_f"))) +
	                   Spr * (FMath::Clamp(Speed / SprintSpeed, 0.6f, 1.3f) / Dur(TEXT("sprint_f")));
	LocoPhase = FMath::Fmod(LocoPhase + Dt * Freq * (LocoIdle < 0.99f ? 1.f : 0.f), 1.f);
	IdleTime += Dt;
}

void AMorphOperative::FillLocomotion(TArray<FMorphTrack, TInlineAllocator<8>>& Out, float W) const
{
	if (W <= 1e-4f)
	{
		return;
	}
	const FMorphClip* Idle = Library->Find(IdleClip());
	if (Idle && LocoIdle > 1e-3f)
	{
		Out.Add({Idle->Seq, FMath::Fmod(IdleTime, Idle->Duration), W * LocoIdle, true, false});
	}
	const float Move = W * (1.f - LocoIdle);
	if (Move <= 1e-4f)
	{
		return;
	}
	// two nearest of the eight directional cycles
	const float A = LastMoveAngle;
	int32 I0 = 0, I1 = 0;
	float T = 0.f;
	for (int32 i = 0; i < 8; ++i)
	{
		const int32 j = (i + 1) % 8;
		const float D0 = FMath::FindDeltaAngleDegrees(DirAngle[i], A);
		const float Span = FMath::FindDeltaAngleDegrees(DirAngle[i], DirAngle[j]);
		if (D0 >= 0.f && D0 <= Span)
		{
			I0 = i;
			I1 = j;
			T = D0 / Span;
			break;
		}
	}
	const float Gait[3] = {1.f - LocoWalkRun, LocoWalkRun * (1.f - LocoSprint), LocoWalkRun * LocoSprint};
	const TCHAR* GaitName[3] = {TEXT("walk"), TEXT("run"), TEXT("sprint")};
	for (int32 g = 0; g < 3; ++g)
	{
		if (Gait[g] <= 1e-3f)
		{
			continue;
		}
		for (int32 k = 0; k < 2; ++k)
		{
			const int32 Di = k == 0 ? I0 : I1;
			const float Wd = k == 0 ? 1.f - T : T;
			if (Wd <= 1e-3f)
			{
				continue;
			}
			FString Id = g == 2 ? TEXT("sprint_f") : FString::Printf(TEXT("%s_%s"), GaitName[g], DirSuffix[Di]);
			const FMorphClip* C = Library->Find(N(Id));
			if (!C)
			{
				continue;
			}
			Out.Add({C->Seq, LocoPhase * C->Duration, Move * Gait[g] * Wd, true, false});
		}
	}
}

void AMorphOperative::TickState(float Dt)
{
	UCharacterMovementComponent* CM = GetCharacterMovement();
	const FMorphSlot* P = Primary();
	auto Next = [this](int32 NewPhase, const TCHAR* Clip, float Blend) {
		Phase = NewPhase;
		PlayFull(N(Clip), Blend);
	};
	switch (State)
	{
	case EMorphState::Locomotion:
		if (CM->IsFalling() && GetVelocity().Z < -250.f)
		{
			EnterState(EMorphState::Airborne, N(TEXT("jump_air")), 0.2f);
			Phase = 1;
		}
		break;
	case EMorphState::Transition:
		if (PrimaryDone(0.12f))
		{
			if (Phase == 10 || Phase == 22)
			{
				AddActorWorldRotation(FRotator(0.f, PendingYaw, 0.f));
				PendingYaw = 0.f;
			}
			if (Phase == 20)
			{
				LocoPhase = 0.516f;    // start_f hands over to walk_f at its authored exit phase
				LocoIdle = 0.f;
			}
			EnterState(EMorphState::Locomotion, NAME_None, Phase == 20 ? 0.1f : 0.2f);
		}
		break;
	case EMorphState::Airborne:
		AirTime = CM->IsFalling() ? AirTime + Dt : 0.f;
		if (Phase == 1 && AirTime > 0.75f)
		{
			Next(2, TEXT("fall"), 0.35f);
		}
		if (Phase == 3 && PrimaryDone(0.1f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.2f);
		}
		break;
	case EMorphState::Dash:
	case EMorphState::Knockback:
	case EMorphState::Emote:
		if (PrimaryDone(0.1f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
		}
		break;
	case EMorphState::Dialogue:
		if (PrimaryDone(0.05f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.3f);
		}
		break;
	case EMorphState::Blink:
		if (Phase == 0 && PrimaryDone(0.02f))
		{
			Next(1, TEXT("blink_in"), 0.05f);
		}
		else if (Phase == 1 && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.15f);
		}
		break;
	case EMorphState::Action:
	{
		const FName Id = PrimaryId();
		// combo handover: after 55 % of the clip and never before its hit window has closed
		float ComboAt = P && P->Clip ? P->Clip->Duration * 0.55f : 0.f;
		if (P && P->Clip)
		{
			for (const FMorphMarker& M : P->Clip->Markers)
			{
				if (M.Name == N(TEXT("hit_end")))
				{
					ComboAt = FMath::Max(ComboAt, M.Time + 0.02f);
				}
			}
		}
		if (bComboQueued && P && P->Clip && P->Time > ComboAt)
		{
			bComboQueued = false;
			if (Id == N(TEXT("melee_1")))
			{
				PlayFull(N(TEXT("melee_2")), 0.08f);
				Trace(TEXT("combo -> melee_2"));
				break;
			}
			if (Id == N(TEXT("melee_2")))
			{
				PlayFull(N(TEXT("melee_3")), 0.08f);
				Trace(TEXT("combo -> melee_3"));
				break;
			}
		}
		if (PrimaryDone(0.1f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
		}
		break;
	}
	case EMorphState::Channel:
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			if (bHeld)
			{
				Next(1, TEXT("channel_loop"), 0.1f);
			}
			else
			{
				Next(2, TEXT("channel_end"), 0.1f);
			}
		}
		else if ((Phase == 2 || Phase == 3) && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.2f);
		}
		break;
	case EMorphState::Charge:
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			if (bHeld)
			{
				Next(1, TEXT("charge_hold"), 0.1f);
			}
			else
			{
				Next(2, TEXT("charge_release"), 0.08f);
			}
		}
		else if ((Phase == 2 || Phase == 3) && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.2f);
		}
		break;
	case EMorphState::Uplink:
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			Next(1, TEXT("uplink_loop"), 0.1f);
		}
		else if (Phase == 1 && StateTime > 2.6f)
		{
			bHeld = false;
			Next(2, TEXT("uplink_end"), 0.1f);
			Trace(TEXT("uplink complete"));
		}
		else if ((Phase == 2 || Phase == 3) && PrimaryDone(0.06f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.2f);
		}
		break;
	case EMorphState::Stun:
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			Next(1, TEXT("stun_loop"), 0.1f);
		}
		else if (Phase == 1 && StateTime > 3.0f)
		{
			Next(2, TEXT("stun_end"), 0.15f);
		}
		else if (Phase == 2 && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.2f);
		}
		break;
	case EMorphState::Sleep:
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			Next(1, TEXT("sleep_loop"), 0.2f);
		}
		else if (Phase == 1 && StateTime > 7.0f)
		{
			Next(2, TEXT("sleep_end"), 0.2f);
		}
		else if (Phase == 2 && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
		}
		break;
	case EMorphState::Knockup:
		if (Phase == 0 && StateTime > 0.12f && !CM->IsFalling() && StateTime < 0.2f)
		{
			LaunchCharacter(FVector(0.f, 0.f, 720.f) - GetActorForwardVector() * 150.f, true, true);
		}
		if (Phase == 0 && PrimaryDone(0.05f))
		{
			Next(1, TEXT("knockup_air"), 0.1f);
		}
		break;
	case EMorphState::Down:
		if (Phase == 0 && PrimaryDone(0.04f))
		{
			Next(1, bFromFront ? TEXT("prone_back") : TEXT("prone_front"), 0.1f);
		}
		else if (Phase == 1 && StateTime > 3.2f)
		{
			Next(2, bFromFront ? TEXT("getup_back") : TEXT("getup_front"), 0.12f);
		}
		else if (Phase == 2 && PrimaryDone(0.08f))
		{
			EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
		}
		break;
	case EMorphState::Dead:
		if (Phase == 0 && PrimaryDone(0.0f))
		{
			// the held dead pose is the exact last frame of the death clip
			Next(1, bFromFront ? TEXT("dead_front") : TEXT("dead_back"), 0.0f);
		}
		break;
	case EMorphState::Respawn:
		if (PrimaryDone(0.1f))
		{
			bDeadOnce = false;
			EnterState(EMorphState::Locomotion, NAME_None, 0.25f);
		}
		break;
	case EMorphState::Preview:
		if (P && P->Clip && !P->Clip->bLoop && PrimaryDone(0.f) && bPreviewLoop)
		{
			PlayFull(P->Clip->Id, 0.15f, 1.f, true);
		}
		break;
	}
	// voluntary actions keep the feet planted: no controller-driven travel
	const bool bLocked = State == EMorphState::Action || State == EMorphState::Channel ||
	                     State == EMorphState::Charge || State == EMorphState::Uplink || State == EMorphState::Stun ||
	                     State == EMorphState::Sleep || State == EMorphState::Dead || State == EMorphState::Down ||
	                     State == EMorphState::Respawn || State == EMorphState::Emote ||
	                     State == EMorphState::Dialogue || State == EMorphState::Preview;
	if (bLocked && !CM->IsFalling() && State != EMorphState::Knockback)
	{
		CM->Velocity = FMath::VInterpTo(CM->Velocity, FVector::ZeroVector, Dt, 12.f);
	}
}

void AMorphOperative::Landed(const FHitResult& Hit)
{
	Super::Landed(Hit);
	const float Vz = FMath::Abs(GetVelocity().Z);
	if (State == EMorphState::Airborne)
	{
		const bool bHeavy = AirTime > 0.9f || Vz > 950.f;
		Phase = 3;
		PlayFull(bHeavy ? N(TEXT("land_heavy")) : N(TEXT("jump_land")), 0.06f);
		Trace(FString::Printf(TEXT("landed %s (air %.2fs)"), bHeavy ? TEXT("heavy") : TEXT("soft"), AirTime));
		AirTime = 0.f;
	}
	else if (State == EMorphState::Knockup)
	{
		bFromFront = true;
		State = EMorphState::Down;
		StateTime = 0.f;
		Phase = 0;
		PlayFull(N(TEXT("knockdown_back")), 0.06f);
		Trace(TEXT("knockup landed -> knockdown_back"));
	}
}

// ===================================================================================== events
void AMorphOperative::OnEvent(FName Clip, FName Event)
{
	++EventCount;
	const FString E = MorphIdStr(Event);
	Trace(FString::Printf(TEXT("event %s @%s"), *E, *MorphIdStr(Clip)));
	if (Event == N(TEXT("takeoff")))
	{
		Phase = 1;
		LaunchCharacter(FVector(0.f, 0.f, GetCharacterMovement()->JumpZVelocity), false, true);
		PlayFull(N(TEXT("jump_air")), 0.12f);
	}
	else if (Event == N(TEXT("blink_teleport")))
	{
		const FVector Dir = GetActorForwardVector();
		FVector Dest = GetActorLocation() + Dir * 500.f;
		GetWorld()->FindTeleportSpot(this, Dest, GetActorRotation());
		SetActorLocation(Dest, false, nullptr, ETeleportType::TeleportPhysics);
		FlashEffect(N(TEXT("sock_fx_ground")), FLinearColor(0.1f, 0.8f, 1.f), 0.9f, 0.12f);
	}
	else if (Event == N(TEXT("beacon_release")))
	{
		SpawnBeaconProp();
	}
	else if (E.StartsWith(TEXT("muzzle_fire")))
	{
		FlashEffect(N(TEXT("sock_muzzle_r")), FLinearColor(1.f, 0.6f, 0.2f), 0.12f, 0.06f);
		const FVector From = GetMesh()->GetSocketLocation(N(TEXT("sock_muzzle_r")));
		const FVector Dir = bAiming ? (AimTarget - From).GetSafeNormal() : GetActorForwardVector();
		DrawDebugLine(GetWorld(), From, From + Dir * 2000.f, Team == 0 ? FColor(30, 220, 255) : FColor(255, 110, 30),
		              false, 0.08f, 0, 1.5f);
	}
	else if (Event == N(TEXT("cast_release")) || Event == N(TEXT("charge_release")) ||
	         Event == N(TEXT("channel_pulse")))
	{
		FlashEffect(N(TEXT("sock_fx_palm_l")), FLinearColor(0.2f, 0.9f, 1.f), 0.35f, 0.2f);
	}
	else if (Event == N(TEXT("hit_start")))
	{
		FlashEffect(N(TEXT("sock_blade_tip_r")), FLinearColor(1.f, 1.f, 1.f), 0.1f, 0.1f);
	}
}

void AMorphOperative::Trace(const FString& Text)
{
	const float T = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
	EventLog.Add({T, Text});
	if (EventLog.Num() > 40)
	{
		EventLog.RemoveAt(0, EventLog.Num() - 40);
	}
	UE_LOG(LogMorph, Log, TEXT("[%8.3f] %s: %s"), T, *GetName(), *Text);
	OnTrace.Broadcast(this, Text);
}

void AMorphOperative::FlashEffect(FName Socket, const FLinearColor& Color, float Scale, float Life)
{
	FxSphere->SetWorldLocation(GetMesh()->GetSocketLocation(Socket));
	FxSphere->SetWorldScale3D(FVector(Scale));
	if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(FxSphere->GetMaterial(0)))
	{
		MID->SetVectorParameterValue(TEXT("Color"), Color * 6.f);
	}
	FxSphere->SetVisibility(true);
	FxLife = Life;
}

void AMorphOperative::SpawnBeaconProp()
{
	UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/MorphRig/Props/SM_Beacon.SM_Beacon"));
	if (!SM)
	{
		return;
	}
	const FTransform T = GetMesh()->GetSocketTransform(N(TEXT("prop_beacon")));
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* A = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), T, P);
	if (A)
	{
		A->SetMobility(EComponentMobility::Movable);
		A->GetStaticMeshComponent()->SetStaticMesh(SM);
		A->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		if (MIDs.Num())
		{
			for (int32 i = 0; i < A->GetStaticMeshComponent()->GetNumMaterials(); ++i)
			{
				UMaterialInstanceDynamic* MI = A->GetStaticMeshComponent()->CreateDynamicMaterialInstance(i);
				if (MI)
				{
					MI->SetScalarParameterValue(TEXT("Team"), float(Team));
				}
			}
		}
		DeployedBeacon = A;
	}
	GetMesh()->HideBoneByName(N(TEXT("prop_beacon")), PBO_None);
	bBeaconHidden = true;
}

void AMorphOperative::ClearProps()
{
	if (DeployedBeacon)
	{
		DeployedBeacon->Destroy();
		DeployedBeacon = nullptr;
	}
	if (bBeaconHidden)
	{
		GetMesh()->UnHideBoneByName(N(TEXT("prop_beacon")));
		bBeaconHidden = false;
	}
}

// ===================================================================================== root motion, IK, look
void AMorphOperative::TickRootMotion(float Dt)
{
	const FMorphSlot* P = Primary();
	if (!P || !P->Clip || !P->Clip->bRootMotion || P->Time <= P->PrevTime)
	{
		return;
	}
	const FAnimExtractContext Ctx(double(P->Time), true, FDeltaTimeRecord(), false);
	const FTransform D = P->Clip->Seq->ExtractRootMotionFromRange(P->PrevTime, P->Time, Ctx);
	const FVector World = GetMesh()->GetComponentTransform().TransformVectorNoScale(D.GetTranslation());
	AddActorWorldOffset(FVector(World.X, World.Y, 0.f), true);
}

void AMorphOperative::TickFootIK(float Dt)
{
	const bool bStanding = !GetCharacterMovement()->IsFalling() &&
	                       (State == EMorphState::Locomotion || State == EMorphState::Transition ||
	                        State == EMorphState::Action || State == EMorphState::Channel ||
	                        State == EMorphState::Charge || State == EMorphState::Uplink ||
	                        State == EMorphState::Emote || State == EMorphState::Dialogue ||
	                        State == EMorphState::Stun || State == EMorphState::Preview);
	IKAlpha = FMath::FInterpConstantTo(IKAlpha, bStanding ? 1.f : 0.f, Dt, 4.f);
	if (IKAlpha <= 0.f)
	{
		return;
	}
	const float HalfH = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const float BaseZ = GetActorLocation().Z - HalfH;
	static const FName Feet[2] = {FName(TEXT("foot_l")), FName(TEXT("foot_r"))};
	float Off[2];
	for (int32 s = 0; s < 2; ++s)
	{
		const FVector F = GetMesh()->GetSocketLocation(Feet[s]);
		FHitResult Hit;
		FCollisionQueryParams Q(SCENE_QUERY_STAT(MorphFootIK), false, this);
		const FVector A(F.X, F.Y, BaseZ + 45.f);
		const FVector B(F.X, F.Y, BaseZ - 45.f);
		float O = 0.f;
		FVector Nw = FVector::UpVector;
		if (GetWorld()->LineTraceSingleByChannel(Hit, A, B, ECC_Visibility, Q))
		{
			O = FMath::Clamp(Hit.ImpactPoint.Z - BaseZ, -30.f, 30.f);
			Nw = Hit.ImpactNormal;
		}
		Off[s] = O;
		const FVector Nc = GetMesh()->GetComponentTransform().InverseTransformVectorNoScale(Nw);
		FootNormal[s] = FMath::VInterpTo(FootNormal[s], Nc, Dt, 10.f);
	}
	const float Pel = FMath::Min(Off[0], Off[1]);
	PelvisOffset = FMath::FInterpTo(PelvisOffset, Pel, Dt, 10.f);
	for (int32 s = 0; s < 2; ++s)
	{
		FootOffset[s] = FMath::FInterpTo(FootOffset[s], Off[s], Dt, 14.f);
	}
}

void AMorphOperative::TickLookAt(float Dt)
{
	float Yaw = 0.f, Pitch = 0.f, Alpha = 0.f;
	const bool bFree = (State == EMorphState::Locomotion && GetSpeedCms() < 60.f && UpperAlpha < 0.1f) ||
	                   State == EMorphState::Preview;
	if (bFree)
	{
		FVector Target = bAiming ? AimTarget : FVector::ZeroVector;
		if (!bAiming)
		{
			if (const APlayerController* PC = GetWorld()->GetFirstPlayerController())
			{
				FVector Loc;
				FRotator Rot;
				PC->GetPlayerViewPoint(Loc, Rot);
				Target = Loc;
			}
		}
		const FVector Eye = GetMesh()->GetSocketLocation(TEXT("head")) + FVector(0, 0, 8.f);
		const FVector L = GetActorTransform().InverseTransformVectorNoScale(Target - Eye);
		Yaw = FMath::RadiansToDegrees(FMath::Atan2(-L.Y, L.X));
		Pitch = FMath::RadiansToDegrees(FMath::Atan2(L.Z, FVector2D(L.X, L.Y).Size()));
		Alpha = FMath::Abs(Yaw) < 100.f ? 1.f : 0.f;
	}
	LookYaw = FMath::FInterpTo(LookYaw, Yaw, Dt, 5.f);
	LookPitch = FMath::FInterpTo(LookPitch, Pitch, Dt, 5.f);
	LookAlpha = FMath::FInterpConstantTo(LookAlpha, Alpha, Dt, 2.5f);
	// aim layer
	AimAlpha = FMath::FInterpConstantTo(AimAlpha, (bAiming && State == EMorphState::Locomotion) ? 1.f : 0.f, Dt, 5.f);
	if (bAiming)
	{
		const FVector From = GetActorLocation() + FVector(0, 0, 50.f);
		const FVector L = GetActorTransform().InverseTransformVectorNoScale(AimTarget - From);
		AimYaw = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(-L.Y, L.X)), -60.f, 60.f);
		AimPitch = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(L.Z, FVector2D(L.X, L.Y).Size())), -35.f, 35.f);
	}
}

void AMorphOperative::BuildRequest()
{
	UMorphAnimInstance* AI = Cast<UMorphAnimInstance>(GetMesh()->GetAnimInstance());
	if (!AI)
	{
		return;
	}
	FMorphPoseRequest& R = AI->Request;
	R = FMorphPoseRequest();
	for (const FMorphSlot& S : Base)
	{
		if (S.bLoco)
		{
			FillLocomotion(R.Base, S.Weight);
		}
		else if (S.Clip)
		{
			R.Base.Add({S.Clip->Seq, S.Time, S.Weight, S.Clip->bLoop, S.Clip->bRootMotion});
		}
	}
	for (const FMorphSlot& S : Upper)
	{
		if (S.Clip)
		{
			R.Upper.Add({S.Clip->Seq, S.Time, S.Weight, S.Clip->bLoop, false});
		}
	}
	R.UpperAlpha = UpperAlpha;
	if (AimAlpha > 1e-3f)
	{
		// bilinear blend of the calibrated grid: yaw -60 / 0 / +60 (left positive), pitch -35 / 0 / +35
		const float U = (AimYaw + 60.f) / 60.f;     // 0 right .. 2 left
		const float V = (AimPitch + 35.f) / 35.f;   // 0 down .. 2 up
		const TCHAR* Cols[3] = {TEXT("right"), TEXT("center"), TEXT("left")};
		const TCHAR* Rows[3] = {TEXT("down"), TEXT("level"), TEXT("up")};
		const int32 C0 = FMath::Clamp(FMath::FloorToInt(U), 0, 1), R0 = FMath::Clamp(FMath::FloorToInt(V), 0, 1);
		const float Fu = FMath::Clamp(U - C0, 0.f, 1.f), Fv = FMath::Clamp(V - R0, 0.f, 1.f);
		for (int32 dr = 0; dr < 2; ++dr)
		{
			for (int32 dc = 0; dc < 2; ++dc)
			{
				const float W = (dc ? Fu : 1.f - Fu) * (dr ? Fv : 1.f - Fv);
				if (W < 1e-3f)
				{
					continue;
				}
				const FMorphClip* C = Library->Find(N(FString::Printf(TEXT("aim_%s_%s"), Rows[R0 + dr], Cols[C0 + dc])));
				if (C)
				{
					R.Aim.Add({C->Seq, 0.f, W, false, false});
				}
			}
		}
		R.AimAlpha = AimAlpha;
	}
	for (const FMorphSlot& S : Additive)
	{
		if (S.Clip)
		{
			R.Additive.Add({S.Clip->Seq, S.Time, S.Weight, false, false});
		}
	}
	// face panel: bone-driven controls as additive control poses, shapes as morph overrides
	for (const TPair<FName, float>& C : FaceControls)
	{
		const FMorphClip* Clip = Library->Find(C.Key);
		if (Clip && C.Value > 1e-3f)
		{
			R.Additive.Add({Clip->Seq, Clip->Duration, C.Value, false, false});
		}
	}
	// idle gaze: eyes follow the look target with the calibrated gaze poses
	if (LookAlpha > 1e-3f && !bFacePanel)
	{
		const float Gy = FMath::Clamp(LookYaw / 30.f, -1.f, 1.f) * LookAlpha;
		const float Gp = FMath::Clamp(LookPitch / 25.f, -1.f, 1.f) * LookAlpha;
		auto AddGaze = [&](const TCHAR* Id, float W) {
			const FMorphClip* Clip = Library->Find(N(Id));
			if (Clip && W > 1e-3f)
			{
				R.Additive.Add({Clip->Seq, Clip->Duration, W * 0.6f, false, false});
			}
		};
		AddGaze(Gy > 0.f ? TEXT("ctl_look_left") : TEXT("ctl_look_right"), FMath::Abs(Gy));
		AddGaze(Gp > 0.f ? TEXT("ctl_look_up") : TEXT("ctl_look_down"), FMath::Abs(Gp));
	}
	if (FaceMorphs.Num())
	{
		for (const TPair<FName, float>& M : FaceMorphs)
		{
			R.Morphs.Add(M);
		}
		R.MorphAlpha = 1.f;
	}
	R.LegIK.Alpha = IKAlpha;
	R.LegIK.PelvisOffset = PelvisOffset;
	R.LegIK.FootOffset[0] = FootOffset[0];
	R.LegIK.FootOffset[1] = FootOffset[1];
	R.LegIK.GroundNormal[0] = FootNormal[0];
	R.LegIK.GroundNormal[1] = FootNormal[1];
	R.LookYaw = LookYaw;
	R.LookPitch = LookPitch;
	R.LookAlpha = LookAlpha * 0.8f;
}

// ===================================================================================== presentation
void AMorphOperative::ApplyTeamToMaterials()
{
	for (UMaterialInstanceDynamic* MI : MIDs)
	{
		if (MI)
		{
			MI->SetScalarParameterValue(TEXT("Team"), float(Team));
		}
	}
}

void AMorphOperative::SetTeam(int32 InTeam)
{
	Team = FMath::Clamp(InTeam, 0, 1);
	ApplyTeamToMaterials();
	GetMesh()->SetCustomDepthStencilValue(1 + Team);
	if (DeployedBeacon)
	{
		if (UStaticMeshComponent* C = Cast<AStaticMeshActor>(DeployedBeacon)->GetStaticMeshComponent())
		{
			for (int32 i = 0; i < C->GetNumMaterials(); ++i)
			{
				if (UMaterialInstanceDynamic* MI = Cast<UMaterialInstanceDynamic>(C->GetMaterial(i)))
				{
					MI->SetScalarParameterValue(TEXT("Team"), float(Team));
				}
			}
		}
	}
}

void AMorphOperative::SetForcedLOD(int32 Lod)
{
	ForcedLOD = FMath::Clamp(Lod, 0, 3);
	GetMesh()->SetForcedLOD(ForcedLOD);   // 0 = automatic, n = LOD n-1
}

void AMorphOperative::SetOutline(bool b)
{
	bOutline = b;
	GetMesh()->SetRenderCustomDepth(b);
	GetMesh()->SetCustomDepthStencilValue(1 + Team);
}

const TArray<FName>& AMorphOperative::MorphNames()
{
	static TArray<FName> Names;
	if (Names.Num() == 0)
	{
		for (const TCHAR* S : {TEXT("browInnerUp_L"), TEXT("browInnerUp_R"), TEXT("browOuterUp_L"), TEXT("browOuterUp_R"),
		                       TEXT("browDown_L"), TEXT("browDown_R"), TEXT("eyeSquint_L"), TEXT("eyeSquint_R"),
		                       TEXT("cheekRaise_L"), TEXT("cheekRaise_R"), TEXT("cheekPuff"), TEXT("noseSneer_L"),
		                       TEXT("noseSneer_R"), TEXT("mouthSmile_L"), TEXT("mouthSmile_R"), TEXT("mouthFrown_L"),
		                       TEXT("mouthFrown_R"), TEXT("mouthStretch_L"), TEXT("mouthStretch_R"), TEXT("mouthPucker"),
		                       TEXT("mouthFunnel"), TEXT("mouthPress"), TEXT("mouthRollUpper"), TEXT("mouthRollLower"),
		                       TEXT("mouthUpperUp_L"), TEXT("mouthUpperUp_R"), TEXT("mouthLowerDown_L"),
		                       TEXT("mouthLowerDown_R"), TEXT("mouthClose"), TEXT("mouthLeft"), TEXT("mouthRight"),
		                       TEXT("V_MBP"), TEXT("V_FV"), TEXT("V_TH"), TEXT("V_LNT"), TEXT("V_SS"), TEXT("V_CH"),
		                       TEXT("V_KG"), TEXT("V_R"), TEXT("V_AA"), TEXT("V_EH"), TEXT("V_EE"), TEXT("V_IH"),
		                       TEXT("V_OH"), TEXT("V_OO")})
		{
			Names.Add(FName(S));
		}
	}
	return Names;
}

const TArray<FName>& AMorphOperative::ControlNames()
{
	static TArray<FName> Names;
	if (Names.Num() == 0)
	{
		for (const TCHAR* S : {TEXT("ctl_blink_l"), TEXT("ctl_blink_r"), TEXT("ctl_wide_l"), TEXT("ctl_wide_r"),
		                       TEXT("ctl_squint_l"), TEXT("ctl_squint_r"), TEXT("ctl_jaw_open"), TEXT("ctl_jaw_left"),
		                       TEXT("ctl_jaw_right"), TEXT("ctl_look_left"), TEXT("ctl_look_right"), TEXT("ctl_look_up"),
		                       TEXT("ctl_look_down"), TEXT("ctl_tongue_up"), TEXT("ctl_tongue_down")})
		{
			Names.Add(FName(S));
		}
	}
	return Names;
}

void AMorphOperative::SetFaceMorph(FName Name, float Value)
{
	if (Value <= 1e-3f)
	{
		FaceMorphs.Remove(Name);
	}
	else
	{
		FaceMorphs.Add(Name, FMath::Clamp(Value, 0.f, 1.f));
	}
}

void AMorphOperative::SetFaceControl(FName Ctl, float Value)
{
	if (Value <= 1e-3f)
	{
		FaceControls.Remove(Ctl);
	}
	else
	{
		FaceControls.Add(Ctl, FMath::Clamp(Value, 0.f, 1.f));
	}
}

void AMorphOperative::ClearFace()
{
	FaceMorphs.Reset();
	FaceControls.Reset();
}

float AMorphOperative::GetFaceMorph(FName Name) const
{
	const float* V = FaceMorphs.Find(Name);
	return V ? *V : 0.f;
}

float AMorphOperative::GetFaceControl(FName Ctl) const
{
	const float* V = FaceControls.Find(Ctl);
	return V ? *V : 0.f;
}

void AMorphOperative::SetAutoPilot(bool b, int32 Seed)
{
	bAutoPilot = b;
	Rng.Initialize(Seed);
	AutoTimer = Rng.FRandRange(0.5f, 2.f);
}

FString AMorphOperative::StateName() const
{
	FString S = UEnum::GetValueAsString(State);
	S.RemoveFromStart(TEXT("EMorphState::"));
	return S;
}

FString AMorphOperative::CurrentClipName() const
{
	const FMorphSlot* P = Primary();
	if (!P)
	{
		return TEXT("-");
	}
	if (P->bLoco)
	{
		if (LocoIdle > 0.5f)
		{
			return MorphIdStr(IdleClip());
		}
		const float A = LastMoveAngle;
		int32 Best = 0;
		for (int32 i = 1; i < 8; ++i)
		{
			if (FMath::Abs(FMath::FindDeltaAngleDegrees(DirAngle[i], A)) <
			    FMath::Abs(FMath::FindDeltaAngleDegrees(DirAngle[Best], A)))
			{
				Best = i;
			}
		}
		const TCHAR* G = LocoSprint > 0.5f ? TEXT("sprint") : (LocoWalkRun > 0.5f ? TEXT("run") : TEXT("walk"));
		return LocoSprint > 0.5f ? FString(TEXT("sprint_f")) : FString::Printf(TEXT("%s_%s (blend)"), G, DirSuffix[Best]);
	}
	return P->Clip ? MorphIdStr(P->Clip->Id) : TEXT("-");
}

float AMorphOperative::CurrentClipTime() const
{
	const FMorphSlot* P = Primary();
	if (!P)
	{
		return 0.f;
	}
	if (P->bLoco)
	{
		return LocoPhase;
	}
	return P->Time;
}

float AMorphOperative::CurrentClipLength() const
{
	const FMorphSlot* P = Primary();
	return (P && P->Clip) ? P->Clip->Duration : 1.f;
}

FString AMorphOperative::DescribeLayers() const
{
	FString S = FString::Printf(TEXT("base %d  upper %.2f (%d)  aim %.2f  add %d  ik %.2f  look %.2f"), Base.Num(),
	                            UpperAlpha, Upper.Num(), AimAlpha, Additive.Num(), IKAlpha, LookAlpha);
	for (const FMorphSlot& U : Upper)
	{
		if (U.Clip && U.Target > 0.f)
		{
			S += FString::Printf(TEXT("  [upper %s %.2fs]"), *U.Clip->Id.ToString(), U.Time);
		}
	}
	return S;
}
