#include "OperativeStateComponent.h"
#include "MorphRig.h"
#include "OperativeCharacter.h"
#include "OperativeAnimInstance.h"
#include "OperativeMovementComponent.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"

TMulticastDelegate<void(const AActor*, const FString&)> UOperativeStateComponent::OnTrace;

namespace OpNames
{
	const FName Root(TEXT("root")), Silence(TEXT("silence")), Disarm(TEXT("disarm")), Stasis(TEXT("stasis"));
	const FName Fear(TEXT("fear")), Charm(TEXT("charm")), Taunt(TEXT("taunt"));
	const FName Melee(TEXT("melee")), Ranged(TEXT("ranged")), Reload(TEXT("reload")), CastDir(TEXT("cast_directional"));
	const FName CastGround(TEXT("cast_ground")), CastSelf(TEXT("cast_self")), Channel(TEXT("channel")), Charge(TEXT("charge"));
	const FName Deploy(TEXT("deploy")), Uplink(TEXT("uplink")), Dash(TEXT("dash")), Blink(TEXT("blink")), Turn(TEXT("turn"));
	const FName Start(TEXT("start")), Stop(TEXT("stop")), Pivot(TEXT("pivot")), Jump(TEXT("jump")), Fall(TEXT("fall")), Land(TEXT("land"));
	const FName Recovery(TEXT("recovery")), ComboWindow(TEXT("combo_window")), ControlRegained(TEXT("control_regained"));
	const FName GroundImpact(TEXT("ground_impact"));
}

static const TCHAR* StateName(EOpState S)
{
	switch (S)
	{
	case EOpState::Locomotion: return TEXT("Locomotion");
	case EOpState::Air: return TEXT("Air");
	case EOpState::Action: return TEXT("Action");
	case EOpState::Emote: return TEXT("Emote");
	case EOpState::Knockback: return TEXT("Knockback");
	case EOpState::Sleep: return TEXT("Sleep");
	case EOpState::Stun: return TEXT("Stun");
	case EOpState::Knockup: return TEXT("Knockup");
	case EOpState::Knockdown: return TEXT("Knockdown");
	case EOpState::Respawn: return TEXT("Respawn");
	case EOpState::Dead: return TEXT("Dead");
	case EOpState::Viewer: return TEXT("Viewer");
	}
	return TEXT("?");
}

/** Transition priority of a full-body state (contract section 5). */
static int32 StatePriority(EOpState S)
{
	switch (S)
	{
	case EOpState::Dead: return 100;
	case EOpState::Respawn: return 90;
	case EOpState::Knockup:
	case EOpState::Knockdown:
	case EOpState::Knockback: return 70;
	case EOpState::Stun: return 60;
	case EOpState::Sleep: return 50;
	case EOpState::Action:
	case EOpState::Emote: return 20;
	case EOpState::Air: return 10;
	default: return 0;
	}
}

UOperativeStateComponent::UOperativeStateComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void UOperativeStateComponent::BeginPlay()
{
	Super::BeginPlay();
	Char = Cast<AOperativeCharacter>(GetOwner());
	Data = &FMorphRigData::Get();
	if (!Char)
	{
		return;
	}
	Move = Cast<UOperativeMovementComponent>(Char->GetCharacterMovement());
	Anim = Cast<UOperativeAnimInstance>(Char->GetMesh()->GetAnimInstance());
	static const FName NAME_Walk(TEXT("walk")), NAME_Run(TEXT("run")), NAME_Sprint(TEXT("sprint"));
	for (const FMorphClip& Clip : Data->Clips)
	{
		if (Clip.Gait == NAME_Walk)
		{
			Walk.Clips.Add(&Clip);
			Walk.Duration = Clip.Duration;
			Walk.Speed = Clip.NominalSpeed;
		}
		else if (Clip.Gait == NAME_Run)
		{
			Run.Clips.Add(&Clip);
			Run.Duration = Clip.Duration;
			Run.Speed = Clip.NominalSpeed;
		}
		else if (Clip.Gait == NAME_Sprint)
		{
			SprintClip = &Clip;
		}
	}
	auto ByAngle = [](const FMorphClip& A, const FMorphClip& B)
	{
		return FRotator::ClampAxis(A.TravelDirDeg) < FRotator::ClampAxis(B.TravelDirDeg);
	};
	Walk.Clips.Sort(ByAngle);
	Run.Clips.Sort(ByAngle);
	Random.Initialize(7919 * (Char->InstanceIndex + 1));
	BlinkTimer = 1.5f + Random.FRand() * 2.5f;
	IdleClip = TEXT("idle_relaxed");
	if (Move)
	{
		// state logic must run before the capsule is moved, the capsule before the pose is evaluated
		Move->AddTickPrerequisiteComponent(this);
	}
}

// ================================================================================================ small helpers
void UOperativeStateComponent::Trace(const FString& Line) const
{
	OnTrace.Broadcast(GetOwner(), FString::Printf(TEXT("[%9.3f] %s"), LocalTime, *Line));
}

void UOperativeStateComponent::Refuse(const TCHAR* What, const TCHAR* Why) const
{
	Trace(FString::Printf(TEXT("REFUSED %s (%s)"), What, Why));
}

bool UOperativeStateComponent::IsGrounded() const
{
	return Move && Move->IsMovingOnGround();
}

bool UOperativeStateComponent::HasFlag(FName Flag) const
{
	return Flags.Contains(Flag);
}

FString UOperativeStateComponent::GetStateText() const
{
	return Tag.IsNone() ? FString(StateName(State)) : FString::Printf(TEXT("%s:%s"), StateName(State), *Tag.ToString());
}

FString UOperativeStateComponent::GetFlagsText() const
{
	FString S;
	for (const FName& F : Flags)
	{
		S += F.ToString().ToUpper() + TEXT(" ");
	}
	if (bWounded)
	{
		S += TEXT("WOUNDED ");
	}
	return S.TrimEnd();
}

FString UOperativeStateComponent::GetLocoText() const
{
	FString S;
	for (const FOpClipSample& Smp : LocoSamples)
	{
		if (Smp.Seq && Smp.Weight > 0.01f)
		{
			S += FString::Printf(TEXT("%s %.2f  "), *Smp.Seq->GetName(), Smp.Weight);
		}
	}
	return S;
}

float UOperativeStateComponent::GetChargeLevel() const
{
	return ChargeTime < 0.f ? 0.f : FMath::Clamp(ChargeTime / 1.5f, 0.f, 1.f);
}

float UOperativeStateComponent::LocalDirDeg(const FVector& WorldDir) const
{
	const FVector Fwd = Char->GetActorForwardVector();
	const FVector Left = -Char->GetActorRightVector();
	return FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(WorldDir, Left), FVector::DotProduct(WorldDir, Fwd)));
}

void UOperativeStateComponent::SetActorYaw(float Yaw)
{
	Char->SetActorRotation(FRotator(0.f, FRotator::NormalizeAxis(Yaw), 0.f));
}

void UOperativeStateComponent::Transition(float Blend)
{
	++TransitionSerial;
	TransitionTime = Blend;
}

void UOperativeStateComponent::SetState(EOpState NewState, FName NewTag)
{
	if (NewState != State || NewTag != Tag)
	{
		Trace(FString::Printf(TEXT("STATE %s -> %s%s%s"), *GetStateText(), StateName(NewState), NewTag.IsNone() ? TEXT("") : TEXT(":"),
			NewTag.IsNone() ? TEXT("") : *NewTag.ToString()));
	}
	State = NewState;
	Tag = NewTag;
}

bool UOperativeStateComponent::StartBase(FName ClipId, EOpState NewState, FName NewTag, float Blend, float StartTime)
{
	const FMorphClip* Info = Data->Find(ClipId);
	UAnimSequence* Seq = Anim ? Anim->GetSequence(ClipId) : nullptr;
	if (!Info || !Seq)
	{
		Trace(FString::Printf(TEXT("ERROR missing clip %s"), *ClipId.ToString()));
		return false;
	}
	if (NewTag != OpNames::Turn && NewTag != OpNames::Pivot)
	{
		RootYawOffset = 0.f;   // an interrupted turn hands its remaining rotation to the inertial blend
	}
	SetState(NewState, NewTag);
	BaseClip.Reset();
	BaseClip.Info = Info;
	BaseClip.Seq = Seq;
	BaseClip.Time = FMath::Clamp(StartTime, 0.f, Info->Duration);
	BaseClip.FiredUpTo = BaseClip.Time - 1.e-4f;
	BaseClip.bLoop = Info->bLoop;
	BaseClip.bUseActionRate = NewState == EOpState::Action;
	BaseClip.ActivationId = ++ActivationCounter;
	Trace(FString::Printf(TEXT("CLIP base %s #%d t=%.3f blend=%.2f"), *ClipId.ToString(), BaseClip.ActivationId, BaseClip.Time, Blend));
	Transition(Blend);
	return true;
}

bool UOperativeStateComponent::StartUpper(FName ClipId, FName NewTag, float Blend)
{
	const FMorphClip* Info = Data->Find(ClipId);
	UAnimSequence* Seq = Anim ? Anim->GetSequence(ClipId) : nullptr;
	if (!Info || !Seq)
	{
		Trace(FString::Printf(TEXT("ERROR missing clip %s"), *ClipId.ToString()));
		return false;
	}
	UpperClip.Reset();
	UpperClip.Info = Info;
	UpperClip.Seq = Seq;
	UpperClip.FiredUpTo = -1.e-4f;
	UpperClip.bLoop = Info->bLoop;
	UpperClip.bUseActionRate = true;
	UpperClip.ActivationId = ++ActivationCounter;
	UpperTag = NewTag;
	CombatTimer = 6.f;
	Trace(FString::Printf(TEXT("CLIP upper %s #%d blend=%.2f speed=%.0f"), *ClipId.ToString(), UpperClip.ActivationId, Blend, GetSpeed()));
	Transition(Blend);
	return true;
}

void UOperativeStateComponent::ClearUpper(float Blend, const TCHAR* Why)
{
	if (!UpperClip.IsValid())
	{
		return;
	}
	Trace(FString::Printf(TEXT("CLIP upper %s #%d ended (%s)"), *UpperClip.Id().ToString(), UpperClip.ActivationId, Why));
	if (UpperTag == OpNames::Reload && !bReloadCounted)
	{
		Trace(TEXT("RELOAD cancelled before reload_insert: no ammo, props return to their mounts"));
	}
	UpperClip.Reset();
	UpperTag = NAME_None;
	ChargeTime = -1.f;
	Transition(Blend);
}

void UOperativeStateComponent::EnterLocomotion(float Blend)
{
	BaseClip.Reset();
	RootYawOffset = 0.f;
	bHitWindow = false;
	bChannelEmitting = false;
	ComboStep = 0;
	bComboBuffered = false;
	if (Move)
	{
		Move->ClearForcedVelocity();
	}
	SetState(EOpState::Locomotion, NAME_None);
	Transition(Blend);
}

// ================================================================================================ clip cursor + markers
void UOperativeStateComponent::Fire(FOpClipPlay& Play, const FMorphEvent& Event)
{
	FOpEventRecord Rec;
	Rec.WorldTime = LocalTime;
	Rec.Clip = Play.Id();
	Rec.Event = Event.Name;
	Rec.ClipTime = Event.Time;
	Rec.ActivationId = Play.ActivationId;
	EventLog.Add(Rec);
	if (EventLog.Num() > 64)
	{
		EventLog.RemoveAt(0, EventLog.Num() - 64);
	}
	++EventCounter;
	Trace(FString::Printf(TEXT("EVENT %s @%.3f clip=%s #%d"), *Event.Name.ToString(), Event.Time, *Play.Id().ToString(), Play.ActivationId));
	const FOpClipPlay Copy = Play;
	HandleEvent(Copy, Event.Name);
	OnEvent.Broadcast(this, Copy, Event.Name);
}

void UOperativeStateComponent::FireRange(FOpClipPlay& Play, float From, float To, bool bIncludeFrom)
{
	const int32 Activation = Play.ActivationId;
	const FMorphClip* Info = Play.Info;
	TArray<const FMorphEvent*, TInlineAllocator<8>> Pending;
	for (const FMorphEvent& E : Info->Events)
	{
		if ((E.Time > From || (bIncludeFrom && E.Time >= From)) && E.Time <= To)
		{
			Pending.Add(&E);
		}
	}
	Play.FiredUpTo = FMath::Max(Play.FiredUpTo, To);
	for (const FMorphEvent* E : Pending)
	{
		if (Play.ActivationId != Activation)
		{
			return;   // the clip was replaced by a handler: its remaining markers are dropped
		}
		Fire(Play, *E);
	}
}

void UOperativeStateComponent::Advance(FOpClipPlay& Play, float DeltaTime)
{
	if (!Play.IsValid() || Play.bFinished)
	{
		return;
	}
	const int32 Activation = Play.ActivationId;
	const float Dur = FMath::Max(Play.Duration(), 1.e-4f);
	const float Rate = Play.Rate * (Play.bUseActionRate ? ActionRate : 1.f);
	float New = Play.Time + DeltaTime * Rate;
	if (Play.bLoop)
	{
		if (New >= Dur)
		{
			FireRange(Play, Play.FiredUpTo, Dur - 1.e-5f, false);
			if (Play.ActivationId != Activation)
			{
				return;
			}
			New = FMath::Fmod(New, Dur);
			++Play.LoopCount;
			Play.FiredUpTo = -1.f;
			Play.Time = New;
			FireRange(Play, 0.f, New, true);
			return;
		}
	}
	else if (New >= Dur)
	{
		New = Dur;
		Play.bFinished = true;
	}
	Play.Time = New;
	FireRange(Play, Play.FiredUpTo, New, false);
}

void UOperativeStateComponent::HandleEvent(const FOpClipPlay& Play, FName Event)
{
	static const FName JumpTakeoff(TEXT("jump_takeoff")), BlinkVanish(TEXT("blink_vanish")), BlinkAppear(TEXT("blink_appear"));
	static const FName HitBegin(TEXT("hit_begin")), HitEnd(TEXT("hit_end")), ReloadInsert(TEXT("reload_insert"));
	static const FName ChargeBegin(TEXT("charge_begin")), ChannelBegin(TEXT("channel_begin")), ChannelComplete(TEXT("channel_complete"));
	static const FName ChannelInterrupted(TEXT("channel_interrupted")), UplinkComplete(TEXT("uplink_complete")), DeployGrab(TEXT("deploy_grab"));
	static const FName DeployRelease(TEXT("deploy_release")), KnockupLaunch(TEXT("knockup_launch"));
	if (State == EOpState::Viewer)
	{
		return;   // the motion viewer shows markers but has no gameplay side effects
	}
	if (Event == JumpTakeoff)
	{
		if (!bJumpLaunched && Move)
		{
			bJumpLaunched = true;
			Char->LaunchCharacter(FVector(0, 0, Move->JumpZVelocity), false, true);
		}
	}
	else if (Event == BlinkVanish)
	{
		Char->SetMeshHiddenForBlink(true);
		Char->SetActorLocation(BlinkDestination, false, nullptr, ETeleportType::TeleportPhysics);
		bResetSecondary = true;
		Trace(FString::Printf(TEXT("TELEPORT to %s"), *BlinkDestination.ToCompactString()));
	}
	else if (Event == BlinkAppear)
	{
		Char->SetMeshHiddenForBlink(false);
	}
	else if (Event == HitBegin)
	{
		bHitWindow = true;
	}
	else if (Event == HitEnd)
	{
		bHitWindow = false;
	}
	else if (Event.ToString().StartsWith(TEXT("muzzle_")))
	{
		Ammo = FMath::Max(0, Ammo - 1);
	}
	else if (Event == ReloadInsert)
	{
		Ammo = 12;
		bReloadCounted = true;
	}
	else if (Event == ChargeBegin)
	{
		ChargeTime = 0.f;
	}
	else if (Event == ChannelBegin)
	{
		bChannelEmitting = true;
		ChannelTime = 0.f;
	}
	else if (Event == ChannelComplete || Event == ChannelInterrupted)
	{
		bChannelEmitting = false;
	}
	else if (Event == UplinkComplete)
	{
		RecallDelay = 0.6f;
	}
	else if (Event == DeployGrab)
	{
		bBeaconGrabbed = true;
	}
	else if (Event == DeployRelease)
	{
		bBeaconGrabbed = false;
		bBeaconDeployed = true;
		BeaconRestock = 8.f;
	}
	else if (Event == KnockupLaunch)
	{
		Char->LaunchCharacter(FVector(0, 0, 720.f), true, true);
	}
}

// ================================================================================================ tick
void UOperativeStateComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (!Char || !Data || !Data->bValid)
	{
		return;
	}
	if (!Anim)
	{
		Anim = Cast<UOperativeAnimInstance>(Char->GetMesh()->GetAnimInstance());
		if (!Anim)
		{
			return;
		}
	}
	++FrameSerial;
	if (Flags.Contains(OpNames::Stasis))
	{
		// stasis: clocks stopped, no markers, pose frozen by the proxy
		Anim->Input.bFrozen = true;
		Anim->Input.FrameSerial = FrameSerial;
		Anim->Input.DeltaTime = 0.f;
		return;
	}
	LocalTime += DeltaTime;
	UpdateState(DeltaTime);
	UpdateMovement(DeltaTime);
	UpdateLocomotionBlend(DeltaTime);
	UpdateAim(DeltaTime);
	UpdateHits(DeltaTime);
	UpdateFace(DeltaTime);
	UpdateFootIK(DeltaTime);
	BuildAnimInput(DeltaTime);
}

void UOperativeStateComponent::UpdateState(float Dt)
{
	CombatTimer = FMath::Max(0.f, CombatTimer - Dt);
	AimHold = FMath::Max(0.f, AimHold - Dt);
	PainPulse = FMath::Max(0.f, PainPulse - Dt * 1.6f);
	if (bBeaconDeployed)
	{
		BeaconRestock -= Dt;
		if (BeaconRestock <= 0.f)
		{
			bBeaconDeployed = false;
			Trace(TEXT("BEACON restocked on the belt"));
		}
	}
	if (ChargeTime >= 0.f)
	{
		ChargeTime += Dt * ActionRate;
	}

	// ---- cursors
	if (BaseClip.IsValid() && !(State == EOpState::Viewer && bViewerPaused))
	{
		const float Scale = State == EOpState::Viewer ? ViewerRate : 1.f;
		Advance(BaseClip, Dt * Scale);
	}
	if (UpperClip.IsValid())
	{
		Advance(UpperClip, Dt);
		if (UpperClip.IsValid() && UpperClip.bFinished)
		{
			OnUpperFinished();
		}
	}

	const bool bMoveCommand = Input.MoveDir.SizeSquared() > 0.09f && CanControl();
	switch (State)
	{
	case EOpState::Locomotion:
		if (BaseClip.IsValid() && BaseClip.bFinished)
		{
			Trace(FString::Printf(TEXT("CLIP base %s #%d finished speed=%.0f"), *BaseClip.Id().ToString(), BaseClip.ActivationId, Speed));
			if (Tag == OpNames::Start || Tag == OpNames::Pivot)
			{
				// hand over to the loop at the foot phase the clip ends on (manifest exit_phase when given)
				if (BaseClip.Info->ExitPhase >= 0.f)
				{
					Phase = FMath::Frac(BaseClip.Info->ExitPhase);
				}
				else if (Tag == OpNames::Start)
				{
					Phase = 0.06f;
				}
			}
			EnterLocomotion(0.15f);
		}
		if (Move && Move->IsFalling())
		{
			FallTime += Dt;
			if (FallTime > 0.12f)
			{
				ApexZ = Char->GetActorLocation().Z;
				StartBase(TEXT("fall"), EOpState::Air, OpNames::Fall, 0.2f);
			}
		}
		else
		{
			FallTime = 0.f;
		}
		if (RecallDelay >= 0.f)
		{
			RecallDelay -= Dt;
			if (RecallDelay < 0.f)
			{
				DoBlink(Char->SpawnLocation);
			}
		}
		break;
	case EOpState::Air:
	{
		const float VZ = Move ? (float)Move->Velocity.Z : 0.f;
		const float Z = (float)Char->GetActorLocation().Z;
		ApexZ = FMath::Max(ApexZ, Z);
		if (Move && Move->IsFalling())
		{
			LastFallSpeed = FMath::Max(0.f, -VZ);
			if (VZ < 0.f)
			{
				FallTime += Dt;
			}
		}
		if (Tag == OpNames::Jump && BaseClip.bFinished)
		{
			StartBase(TEXT("jump_air"), EOpState::Air, TEXT("jump_air"), 0.12f);
		}
		else if (Tag == FName(TEXT("jump_air")) && (FallTime > 0.45f || ApexZ - Z > 150.f))
		{
			StartBase(TEXT("fall"), EOpState::Air, OpNames::Fall, 0.25f);
		}
		else if (Tag == OpNames::Land && BaseClip.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		else if (Tag == OpNames::Land && bMoveCommand && BaseClip.Time > BaseClip.Duration() * 0.6f)
		{
			EnterLocomotion(0.2f);
		}
		else if (Tag != OpNames::Land && Tag != OpNames::Jump && IsGrounded())
		{
			NotifyLanded(LastFallSpeed);   // safety net when the Landed callback was missed
		}
		else if (Tag == OpNames::Jump && BaseClip.Time > 0.05f && !bJumpLaunched && Move && Move->IsFalling())
		{
			bJumpLaunched = true;
		}
		break;
	}
	case EOpState::Action:
		if (Tag == OpNames::Melee)
		{
			const float ComboT = BaseClip.Info->EventTime(OpNames::ComboWindow, BaseClip.Duration() + 1.f);
			const float RecT = BaseClip.Info->EventTime(OpNames::Recovery, BaseClip.Duration());
			if (bComboBuffered && ComboStep < 3 && BaseClip.Time >= ComboT)
			{
				bComboBuffered = false;
				++ComboStep;
				bHitWindow = false;
				StartBase(FName(*FString::Printf(TEXT("melee_%d"), ComboStep)), EOpState::Action, OpNames::Melee, 0.1f);
				break;
			}
			if (bMoveCommand && BaseClip.Time >= RecT)
			{
				Trace(TEXT("MELEE tail cancelled by movement after recovery"));
				EnterLocomotion(0.2f);
				break;
			}
		}
		else if (Tag == OpNames::CastGround || Tag == OpNames::CastSelf)
		{
			const float RecT = BaseClip.Info->EventTime(OpNames::Recovery, BaseClip.Duration());
			if (bMoveCommand && BaseClip.Time >= RecT)
			{
				EnterLocomotion(0.2f);
				break;
			}
		}
		else if (Tag == OpNames::Channel)
		{
			const FName Id = BaseClip.Id();
			if (Id == FName(TEXT("channel_start")) || Id == FName(TEXT("channel_loop")))
			{
				if (bChannelEmitting)
				{
					ChannelTime += Dt * ActionRate;
				}
				if (bMoveCommand)
				{
					ChannelInterrupt(TEXT("movement command"));
					break;
				}
				if (ChannelTime >= 4.f)
				{
					Trace(TEXT("CHANNEL reached its 4 s limit"));
					ChannelRelease();
					break;
				}
			}
		}
		else if (Tag == OpNames::Uplink)
		{
			const FName Id = BaseClip.Id();
			if (Id == FName(TEXT("uplink_start")) || Id == FName(TEXT("uplink_loop")))
			{
				if (bMoveCommand)
				{
					UplinkCancel(TEXT("movement command"));
					break;
				}
				if (Id == FName(TEXT("uplink_loop")))
				{
					UplinkTime += Dt * ActionRate;
					if (UplinkTime >= 3.f)
					{
						StartBase(TEXT("uplink_end"), EOpState::Action, OpNames::Uplink, 0.15f);
						break;
					}
				}
			}
		}
		else if (Tag == OpNames::Dash && Move && BaseClip.IsValid())
		{
			// root track delta of this tick drives the capsule through the movement component
			const float T1 = BaseClip.Time;
			const float T0 = FMath::Max(0.f, T1 - Dt * ActionRate);
			if (T1 > T0 && Dt > 1.e-5f && !BaseClip.bFinished)
			{
				const FAnimExtractContext Ctx((double)T1, true);
				const FTransform Delta = BaseClip.Seq->ExtractRootMotionFromRange(T0, T1, Ctx);
				const FVector World = Char->GetMesh()->GetComponentTransform().TransformVector(Delta.GetTranslation());
				Move->SetForcedVelocity(World / Dt);
			}
			else
			{
				Move->SetForcedVelocity(FVector::ZeroVector);
			}
		}
		if (BaseClip.IsValid() && BaseClip.bFinished && State == EOpState::Action)
		{
			OnBaseFinished();
		}
		break;
	case EOpState::Emote:
		if (bMoveCommand)
		{
			Trace(TEXT("EMOTE cancelled by movement"));
			Char->StopDialogueAudio();
			EnterLocomotion(0.25f);
		}
		else if (BaseClip.bFinished)
		{
			EnterLocomotion(0.25f);
		}
		break;
	case EOpState::Knockback:
		if (Move)
		{
			const float A = 1.f - FMath::Clamp(BaseClip.Time / FMath::Max(0.05f, BaseClip.Info->EventTime(OpNames::ControlRegained, BaseClip.Duration()) * 0.7f), 0.f, 1.f);
			Move->SetForcedVelocity(KnockDir * 900.f * A * A);
		}
		if (BaseClip.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	case EOpState::Stun:
		if (BaseClip.Id() == FName(TEXT("stun_start")) && BaseClip.bFinished)
		{
			StartBase(TEXT("stun_loop"), EOpState::Stun, NAME_None, 0.15f);
		}
		else if (BaseClip.Id() == FName(TEXT("stun_loop")))
		{
			StunRemaining -= Dt;
			if (StunRemaining <= 0.f)
			{
				StartBase(TEXT("stun_end"), EOpState::Stun, NAME_None, 0.15f);
			}
		}
		else if (BaseClip.Id() == FName(TEXT("stun_end")) && BaseClip.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	case EOpState::Sleep:
		if (BaseClip.Id() == FName(TEXT("sleep_start")) && BaseClip.bFinished)
		{
			StartBase(TEXT("sleep_loop"), EOpState::Sleep, NAME_None, 0.2f);
		}
		else if (BaseClip.Id() == FName(TEXT("sleep_loop")))
		{
			SleepRemaining -= Dt;
			if (SleepRemaining <= 0.f)
			{
				StartBase(TEXT("sleep_end"), EOpState::Sleep, NAME_None, 0.2f);
			}
		}
		else if (BaseClip.Id() == FName(TEXT("sleep_end")) && BaseClip.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	case EOpState::Knockup:
		if (Move && Move->IsFalling())
		{
			LastFallSpeed = FMath::Max(0.f, -(float)Move->Velocity.Z);
		}
		if (BaseClip.Id() == FName(TEXT("knockup_start")) && BaseClip.bFinished)
		{
			StartBase(TEXT("knockup_air"), EOpState::Knockup, NAME_None, 0.15f);
		}
		else if (BaseClip.Id() == FName(TEXT("knockup_air")) && IsGrounded() && BaseClip.LoopCount + BaseClip.Time > 0.1f)
		{
			NotifyLanded(LastFallSpeed);
		}
		break;
	case EOpState::Knockdown:
	{
		const FName Id = BaseClip.Id();
		const bool bDownClip = Id == FName(TEXT("knockdown_front")) || Id == FName(TEXT("knockdown_back"));
		const bool bProne = Id == FName(TEXT("prone_front")) || Id == FName(TEXT("prone_back"));
		if (bDownClip && BaseClip.bFinished)
		{
			ProneRemaining = 1.2f;
			StartBase(bProneFaceUp ? TEXT("prone_back") : TEXT("prone_front"), EOpState::Knockdown, NAME_None, 0.15f);
		}
		else if (bProne)
		{
			ProneRemaining -= Dt;
			if (ProneRemaining <= 0.f)
			{
				StartBase(bProneFaceUp ? TEXT("getup_back") : TEXT("getup_front"), EOpState::Knockdown, NAME_None, 0.2f);
			}
		}
		else if (!bDownClip && BaseClip.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	}
	case EOpState::Respawn:
		if (BaseClip.bFinished)
		{
			EnterLocomotion(0.25f);
		}
		break;
	case EOpState::Dead:
		if (BaseClip.bFinished && !BaseClip.Info->bPose && !BaseClip.Info->FinalPose.IsNone())
		{
			// the held pose is the final frame of the death clip: switch without any blend
			StartBase(BaseClip.Info->FinalPose, EOpState::Dead, Tag, 0.f);
		}
		break;
	case EOpState::Viewer:
		if (BaseClip.IsValid() && BaseClip.bFinished && bViewerLoop && !BaseClip.Info->bPose && !bViewerPaused)
		{
			const FName Id = BaseClip.Id();
			if (BaseClip.Info->bRootMotion)
			{
				Char->SetActorLocation(Char->ViewerLocation, false, nullptr, ETeleportType::TeleportPhysics);
				bResetSecondary = true;
			}
			StartBase(Id, EOpState::Viewer, Id, 0.f);
		}
		if (BaseClip.IsValid() && BaseClip.Info->bRootMotion && Move && !bViewerPaused)
		{
			const float T1 = BaseClip.Time;
			const float T0 = FMath::Max(0.f, T1 - Dt * ViewerRate);
			if (T1 > T0 && Dt > 1.e-5f && !BaseClip.bFinished)
			{
				const FAnimExtractContext Ctx((double)T1, true);
				const FTransform Delta = BaseClip.Seq->ExtractRootMotionFromRange(T0, T1, Ctx);
				Move->SetForcedVelocity(Char->GetMesh()->GetComponentTransform().TransformVector(Delta.GetTranslation()) / Dt);
			}
			else
			{
				Move->SetForcedVelocity(FVector::ZeroVector);
			}
		}
		break;
	}
}

void UOperativeStateComponent::OnBaseFinished()
{
	const FName Id = BaseClip.Id();
	Trace(FString::Printf(TEXT("CLIP base %s #%d finished"), *Id.ToString(), BaseClip.ActivationId));
	if (Tag == OpNames::Channel && Id == FName(TEXT("channel_start")))
	{
		StartBase(TEXT("channel_loop"), EOpState::Action, OpNames::Channel, 0.12f);
	}
	else if (Tag == OpNames::Uplink && Id == FName(TEXT("uplink_start")))
	{
		UplinkTime = 0.f;
		StartBase(TEXT("uplink_loop"), EOpState::Action, OpNames::Uplink, 0.12f);
	}
	else if (Tag == OpNames::Blink && Id == FName(TEXT("blink_out")))
	{
		StartBase(TEXT("blink_in"), EOpState::Action, OpNames::Blink, 0.f);
	}
	else
	{
		EnterLocomotion(0.2f);
	}
}

void UOperativeStateComponent::OnUpperFinished()
{
	const FName Id = UpperClip.Id();
	if (UpperTag == OpNames::Charge && Id == FName(TEXT("charge_start")))
	{
		StartUpper(TEXT("charge_hold"), OpNames::Charge, 0.12f);
		return;
	}
	ClearUpper(0.2f, TEXT("finished"));
}

// ================================================================================================ interruption rules
bool UOperativeStateComponent::CanControl() const
{
	if (State != EOpState::Locomotion && State != EOpState::Air && State != EOpState::Action && State != EOpState::Emote)
	{
		return false;
	}
	return !Flags.Contains(OpNames::Fear) && !Flags.Contains(OpNames::Charm) && !Flags.Contains(OpNames::Taunt);
}

bool UOperativeStateComponent::CanStartAction(const TCHAR* What) const
{
	if (State == EOpState::Viewer)
	{
		return true;   // leaving the viewer is handled by the caller
	}
	if (!CanControl())
	{
		Refuse(What, TEXT("no control in the current state"));
		return false;
	}
	if (State == EOpState::Locomotion)
	{
		return true;
	}
	if (State == EOpState::Emote)
	{
		return true;
	}
	if (State == EOpState::Action && BaseClip.IsValid())
	{
		const float RecT = BaseClip.Info->EventTime(OpNames::Recovery, -1.f);
		if (RecT >= 0.f && BaseClip.Time >= RecT)
		{
			return true;   // tail after the recovery marker may be cancelled by another action
		}
	}
	Refuse(What, TEXT("busy"));
	return false;
}

void UOperativeStateComponent::CancelSoftActions(const TCHAR* Why)
{
	if (UpperClip.IsValid())
	{
		ClearUpper(0.12f, Why);
	}
	if (State == EOpState::Emote)
	{
		Char->StopDialogueAudio();
	}
	if (State == EOpState::Viewer && Move)
	{
		Move->ClearForcedVelocity();
	}
}

void UOperativeStateComponent::InterruptForDisable(const TCHAR* Why)
{
	if (State == EOpState::Action || State == EOpState::Emote)
	{
		Trace(FString::Printf(TEXT("INTERRUPT %s by %s (no exit clip)"), *GetStateText(), Why));
	}
	if (ChargeTime >= 0.f)
	{
		Trace(TEXT("CHARGE dropped without cancel clip"));
	}
	CancelSoftActions(Why);
	bHitWindow = false;
	bChannelEmitting = false;
	ComboStep = 0;
	bComboBuffered = false;
	RootYawOffset = 0.f;
	RecallDelay = -1.f;
	Char->SetMeshHiddenForBlink(false);
	if (Move)
	{
		Move->ClearForcedVelocity();
	}
}

// ================================================================================================ commands
bool UOperativeStateComponent::DoJump()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (!CanControl() || State != EOpState::Locomotion || !IsGrounded() || BaseClip.IsValid())
	{
		Refuse(TEXT("jump"), TEXT("not in grounded locomotion"));
		return false;
	}
	if (Flags.Contains(OpNames::Root))
	{
		Refuse(TEXT("jump"), TEXT("rooted"));
		return false;
	}
	bJumpLaunched = false;
	FallTime = 0.f;
	LastFallSpeed = 0.f;
	ApexZ = (float)Char->GetActorLocation().Z;
	return StartBase(TEXT("jump_start"), EOpState::Air, OpNames::Jump, 0.1f);
}

bool UOperativeStateComponent::DoDash(float DirDeg)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (!CanStartAction(TEXT("dash")))
	{
		return false;
	}
	if (!IsGrounded() || Flags.Contains(OpNames::Root))
	{
		Refuse(TEXT("dash"), Flags.Contains(OpNames::Root) ? TEXT("rooted") : TEXT("airborne"));
		return false;
	}
	const float D = FRotator::NormalizeAxis(DirDeg);
	const TCHAR* Clip = FMath::Abs(D) <= 45.f ? TEXT("dash_f") : (FMath::Abs(D) >= 135.f ? TEXT("dash_b") : (D > 0.f ? TEXT("dash_l") : TEXT("dash_r")));
	CancelSoftActions(TEXT("dash"));
	return StartBase(Clip, EOpState::Action, OpNames::Dash, 0.08f);
}

bool UOperativeStateComponent::DoBlink(const FVector& Destination)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (!CanStartAction(TEXT("blink")))
	{
		return false;
	}
	if (Flags.Contains(OpNames::Root))
	{
		Refuse(TEXT("blink"), TEXT("rooted"));
		return false;
	}
	BlinkDestination = Destination;
	CancelSoftActions(TEXT("blink"));
	return StartBase(TEXT("blink_out"), EOpState::Action, OpNames::Blink, 0.08f);
}

bool UOperativeStateComponent::DoMelee()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Disarm))
	{
		Refuse(TEXT("melee"), TEXT("disarmed"));
		return false;
	}
	if (State == EOpState::Action && Tag == OpNames::Melee)
	{
		if (ComboStep >= 3)
		{
			Refuse(TEXT("melee"), TEXT("combo finished"));
			return false;
		}
		bComboBuffered = true;   // chains at combo_window (immediately when already inside it)
		Trace(TEXT("MELEE combo input buffered"));
		return true;
	}
	if (!CanStartAction(TEXT("melee")) || !IsGrounded())
	{
		return false;
	}
	CancelSoftActions(TEXT("melee"));
	ComboStep = 1;
	bComboBuffered = false;
	CombatTimer = 6.f;
	return StartBase(TEXT("melee_1"), EOpState::Action, OpNames::Melee, 0.1f);
}

bool UOperativeStateComponent::DoRanged(bool bBurst)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Disarm))
	{
		Refuse(TEXT("ranged"), TEXT("disarmed"));
		return false;
	}
	if (!CanControl() || (State != EOpState::Locomotion && State != EOpState::Air))
	{
		Refuse(TEXT("ranged"), TEXT("needs locomotion or air state"));
		return false;
	}
	if (UpperClip.IsValid())
	{
		if (UpperTag == OpNames::Ranged)
		{
			const float RecT = UpperClip.Info->EventTime(OpNames::Recovery, UpperClip.Duration());
			if (UpperClip.Time < RecT)
			{
				Refuse(TEXT("ranged"), TEXT("previous shot not recovered"));
				return false;
			}
		}
		else
		{
			Refuse(TEXT("ranged"), UpperTag == OpNames::Reload ? TEXT("reloading") : TEXT("upper body busy"));
			return false;
		}
	}
	if (Ammo < (bBurst ? 3 : 1))
	{
		Trace(TEXT("RANGED out of ammo -> reload"));
		return DoReload();
	}
	AimAlpha = 1.f;
	AimHold = 1.2f;
	return StartUpper(bBurst ? TEXT("ranged_burst") : TEXT("ranged_fire"), OpNames::Ranged, 0.08f);
}

bool UOperativeStateComponent::DoReload()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (!CanControl() || (State != EOpState::Locomotion))
	{
		Refuse(TEXT("reload"), TEXT("needs locomotion state"));
		return false;
	}
	if (UpperClip.IsValid())
	{
		Refuse(TEXT("reload"), TEXT("upper body busy"));
		return false;
	}
	bReloadCounted = false;
	return StartUpper(TEXT("reload"), OpNames::Reload, 0.15f);
}

bool UOperativeStateComponent::DoCast(FName Kind)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Silence))
	{
		Refuse(TEXT("cast"), TEXT("silenced"));
		return false;
	}
	if (Kind == FName(TEXT("directional")))
	{
		if (!CanControl() || (State != EOpState::Locomotion && State != EOpState::Air) || UpperClip.IsValid())
		{
			Refuse(TEXT("cast_directional"), TEXT("upper body busy or no control"));
			return false;
		}
		AimAlpha = 1.f;
		AimHold = 1.2f;
		return StartUpper(TEXT("cast_directional"), OpNames::CastDir, 0.1f);
	}
	if (!CanStartAction(TEXT("cast")) || !IsGrounded())
	{
		return false;
	}
	CancelSoftActions(TEXT("cast"));
	CombatTimer = 6.f;
	if (Kind == FName(TEXT("ground")))
	{
		return StartBase(TEXT("cast_ground"), EOpState::Action, OpNames::CastGround, 0.12f);
	}
	return StartBase(TEXT("cast_self"), EOpState::Action, OpNames::CastSelf, 0.12f);
}

bool UOperativeStateComponent::ChannelPress()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Silence))
	{
		Refuse(TEXT("channel"), TEXT("silenced"));
		return false;
	}
	if (State == EOpState::Action && Tag == OpNames::Channel)
	{
		return false;
	}
	if (!CanStartAction(TEXT("channel")) || !IsGrounded())
	{
		return false;
	}
	CancelSoftActions(TEXT("channel"));
	ChannelTime = 0.f;
	bChannelEmitting = false;
	CombatTimer = 6.f;
	return StartBase(TEXT("channel_start"), EOpState::Action, OpNames::Channel, 0.12f);
}

bool UOperativeStateComponent::ChannelRelease()
{
	if (State != EOpState::Action || Tag != OpNames::Channel)
	{
		return false;
	}
	const FName Id = BaseClip.Id();
	if (Id != FName(TEXT("channel_start")) && Id != FName(TEXT("channel_loop")))
	{
		return false;
	}
	Trace(FString::Printf(TEXT("CHANNEL released normally at %s t=%.3f"), *Id.ToString(), BaseClip.Time));
	// leave the emission flag on until channel_complete fires inside channel_end
	return StartBase(TEXT("channel_end"), EOpState::Action, OpNames::Channel, 0.15f);
}

bool UOperativeStateComponent::ChannelInterrupt(const TCHAR* Reason)
{
	if (State != EOpState::Action || Tag != OpNames::Channel)
	{
		return false;
	}
	const FName Id = BaseClip.Id();
	if (Id != FName(TEXT("channel_start")) && Id != FName(TEXT("channel_loop")))
	{
		return false;
	}
	Trace(FString::Printf(TEXT("CHANNEL interrupted (%s) at %s t=%.3f"), Reason, *Id.ToString(), BaseClip.Time));
	return StartBase(TEXT("channel_interrupt"), EOpState::Action, OpNames::Channel, 0.1f);
}

bool UOperativeStateComponent::ChargePress()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Silence) || Flags.Contains(OpNames::Disarm))
	{
		Refuse(TEXT("charge"), TEXT("silenced or disarmed"));
		return false;
	}
	if (!CanControl() || (State != EOpState::Locomotion && State != EOpState::Air) || UpperClip.IsValid())
	{
		Refuse(TEXT("charge"), TEXT("upper body busy or no control"));
		return false;
	}
	ChargeTime = -1.f;
	AimAlpha = 1.f;
	AimHold = 1.f;
	return StartUpper(TEXT("charge_start"), OpNames::Charge, 0.12f);
}

bool UOperativeStateComponent::ChargeRelease()
{
	if (!UpperClip.IsValid() || UpperTag != OpNames::Charge)
	{
		return false;
	}
	const FName Id = UpperClip.Id();
	if (Id != FName(TEXT("charge_start")) && Id != FName(TEXT("charge_hold")))
	{
		return false;
	}
	if (ChargeTime < 0.f)
	{
		return ChargeCancel(TEXT("released before charge_begin"));
	}
	ChargeReleaseLevel = GetChargeLevel();
	Trace(FString::Printf(TEXT("CHARGE release requested at level %.2f (%s t=%.3f)"), ChargeReleaseLevel, *Id.ToString(), UpperClip.Time));
	AimHold = 1.2f;
	const bool bOk = StartUpper(TEXT("charge_release"), OpNames::Charge, 0.1f);
	ChargeTime = -1.f;
	return bOk;
}

bool UOperativeStateComponent::ChargeCancel(const TCHAR* Reason)
{
	if (!UpperClip.IsValid() || UpperTag != OpNames::Charge)
	{
		return false;
	}
	const FName Id = UpperClip.Id();
	if (Id != FName(TEXT("charge_start")) && Id != FName(TEXT("charge_hold")))
	{
		return false;
	}
	Trace(FString::Printf(TEXT("CHARGE cancelled (%s) at level %.2f"), Reason, GetChargeLevel()));
	ChargeTime = -1.f;
	return StartUpper(TEXT("charge_cancel"), OpNames::Charge, 0.12f);
}

bool UOperativeStateComponent::DoDeploy()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (bBeaconDeployed)
	{
		Refuse(TEXT("deploy"), TEXT("beacon not restocked yet"));
		return false;
	}
	if (!CanStartAction(TEXT("deploy")) || !IsGrounded())
	{
		return false;
	}
	CancelSoftActions(TEXT("deploy"));
	bBeaconGrabbed = false;
	return StartBase(TEXT("deploy"), EOpState::Action, OpNames::Deploy, 0.15f);
}

bool UOperativeStateComponent::UplinkStart()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (Flags.Contains(OpNames::Silence))
	{
		Refuse(TEXT("uplink"), TEXT("silenced"));
		return false;
	}
	if (State == EOpState::Action && Tag == OpNames::Uplink)
	{
		return false;
	}
	if (!CanStartAction(TEXT("uplink")) || !IsGrounded())
	{
		return false;
	}
	CancelSoftActions(TEXT("uplink"));
	UplinkTime = 0.f;
	return StartBase(TEXT("uplink_start"), EOpState::Action, OpNames::Uplink, 0.15f);
}

bool UOperativeStateComponent::UplinkCancel(const TCHAR* Reason)
{
	if (State != EOpState::Action || Tag != OpNames::Uplink)
	{
		return false;
	}
	const FName Id = BaseClip.Id();
	if (Id != FName(TEXT("uplink_start")) && Id != FName(TEXT("uplink_loop")))
	{
		return false;
	}
	Trace(FString::Printf(TEXT("UPLINK cancelled (%s) at %s t=%.3f"), Reason, *Id.ToString(), BaseClip.Time));
	return StartBase(TEXT("uplink_cancel"), EOpState::Action, OpNames::Uplink, 0.1f);
}

bool UOperativeStateComponent::DoTurn(float YawDeg)
{
	if (State != EOpState::Locomotion || BaseClip.IsValid() || !IsGrounded() || !CanControl())
	{
		return false;
	}
	const bool bLeft = YawDeg > 0.f;
	const FMorphClip* Info = Data->Find(bLeft ? TEXT("turn_l90") : TEXT("turn_r90"));
	if (!Info)
	{
		return false;
	}
	// actor yaw snaps (Unreal yaw is clockwise, the contract's turn angle is counter-clockwise) and the mesh is
	// counter-rotated by the same amount for the duration of the clip, which itself contains the body turn
	SetActorYaw((float)Char->GetActorRotation().Yaw - Info->TurnYawDeg);
	RootYawOffset = Info->TurnYawDeg;
	return StartBase(Info->Id, EOpState::Locomotion, OpNames::Turn, 0.1f);
}

bool UOperativeStateComponent::PlayEmote(FName ClipId)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (!CanControl() || State != EOpState::Locomotion || !IsGrounded())
	{
		Refuse(TEXT("emote"), TEXT("needs idle"));
		return false;
	}
	CancelSoftActions(TEXT("emote"));
	return StartBase(ClipId, EOpState::Emote, ClipId, 0.25f);
}

void UOperativeStateComponent::AddHitInstance(FName ClipId, float Weight, bool bLoopForViewer)
{
	const FMorphClip* Info = Data->Find(ClipId);
	UAnimSequence* Seq = Anim ? Anim->GetSequence(ClipId) : nullptr;
	if (!Info || !Seq || Weight <= 0.01f)
	{
		return;
	}
	if (Hits.Num() >= 8)
	{
		Hits.RemoveAt(0);
	}
	FOpHitInstance H;
	H.Seq = Seq;
	H.Info = Info;
	H.Weight = Weight;
	H.bLoopForViewer = bLoopForViewer;
	Hits.Add(H);
}

void UOperativeStateComponent::ApplyHit(float FromDeg, bool bHeavy)
{
	if (State == EOpState::Dead || State == EOpState::Respawn || Flags.Contains(OpNames::Stasis))
	{
		Trace(TEXT("HIT ignored (dead, respawning or in stasis)"));
		return;
	}
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	// directional blend of the two adjacent additive clips (clips and their directions come from the manifest: layer "additive", hit_from_deg)
	static const FName NAME_AdditiveLayer(TEXT("additive"));
	FString Used;
	for (const FMorphClip& D : Data->Clips)
	{
		if (D.Layer != NAME_AdditiveLayer)
		{
			continue;
		}
		const float Delta = FMath::Abs(FRotator::NormalizeAxis(FromDeg - D.HitFromDeg));
		const float W = FMath::Clamp(1.f - Delta / 90.f, 0.f, 1.f);
		AddHitInstance(D.Id, W);
		if (W > 0.01f)
		{
			Used += FString::Printf(TEXT(" %s=%.2f"), *D.Id.ToString(), W);
		}
	}
	PainPulse = 1.f;
	CombatTimer = 6.f;
	Char->PulseHitFlash();
	Trace(FString::Printf(TEXT("HIT from %.0f deg%s over %s, speed=%.0f, additive clips:%s"), FromDeg, bHeavy ? TEXT(" (heavy)") : TEXT(""), *GetStateText(), GetSpeed(), *Used));
	if (State == EOpState::Sleep && BaseClip.Id() != FName(TEXT("sleep_end")))
	{
		Trace(TEXT("SLEEP broken by damage"));
		StartBase(TEXT("sleep_end"), EOpState::Sleep, NAME_None, 0.15f);
	}
	UplinkCancel(TEXT("damage"));
	if (bHeavy)
	{
		ChannelInterrupt(TEXT("heavy hit"));
	}
}

bool UOperativeStateComponent::ApplyStun(float Duration)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (StatePriority(State) > StatePriority(EOpState::Stun))
	{
		Refuse(TEXT("stun"), TEXT("higher priority state active"));
		return false;
	}
	InterruptForDisable(TEXT("stun"));
	StunRemaining = Duration;
	return StartBase(TEXT("stun_start"), EOpState::Stun, NAME_None, 0.12f);
}

bool UOperativeStateComponent::ApplySleep(float Duration)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (StatePriority(State) > StatePriority(EOpState::Sleep) || !IsGrounded())
	{
		Refuse(TEXT("sleep"), TEXT("higher priority state active or airborne"));
		return false;
	}
	InterruptForDisable(TEXT("sleep"));
	SleepRemaining = Duration;
	return StartBase(TEXT("sleep_start"), EOpState::Sleep, NAME_None, 0.2f);
}

bool UOperativeStateComponent::ApplyKnockback(float FromDeg)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (StatePriority(State) > StatePriority(EOpState::Knockback))
	{
		Refuse(TEXT("knockback"), TEXT("higher priority state active"));
		return false;
	}
	InterruptForDisable(TEXT("knockback"));
	// travel away from the source; the host (movement component) carries the capsule
	const float Rad = FMath::DegreesToRadians(FromDeg);
	const FVector Fwd = Char->GetActorForwardVector(), Left = -Char->GetActorRightVector();
	KnockDir = -(Fwd * FMath::Cos(Rad) + Left * FMath::Sin(Rad)).GetSafeNormal2D();
	return StartBase(TEXT("knockback"), EOpState::Knockback, NAME_None, 0.1f);
}

bool UOperativeStateComponent::ApplyKnockup()
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (StatePriority(State) > StatePriority(EOpState::Knockup))
	{
		Refuse(TEXT("knockup"), TEXT("higher priority state active"));
		return false;
	}
	InterruptForDisable(TEXT("knockup"));
	LastFallSpeed = 0.f;
	return StartBase(TEXT("knockup_start"), EOpState::Knockup, NAME_None, 0.1f);
}

bool UOperativeStateComponent::ApplyKnockdown(bool bHitFromFront)
{
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	if (StatePriority(State) > StatePriority(EOpState::Knockdown))
	{
		Refuse(TEXT("knockdown"), TEXT("higher priority state active"));
		return false;
	}
	InterruptForDisable(TEXT("knockdown"));
	bProneFaceUp = bHitFromFront;   // a hit from the front throws the character onto the back (face-up)
	Trace(FString::Printf(TEXT("KNOCKDOWN hit from %s -> %s"), bHitFromFront ? TEXT("front") : TEXT("behind"), bProneFaceUp ? TEXT("knockdown_back") : TEXT("knockdown_front")));
	return StartBase(bProneFaceUp ? TEXT("knockdown_back") : TEXT("knockdown_front"), EOpState::Knockdown, NAME_None, 0.12f);
}

bool UOperativeStateComponent::Kill(bool bHitFromFront)
{
	if (State == EOpState::Dead)
	{
		Refuse(TEXT("death"), TEXT("already dead - death occurs once"));
		return false;
	}
	if (State == EOpState::Viewer)
	{
		ExitViewer();
	}
	const bool bWasProne = State == EOpState::Knockdown && BaseClip.IsValid() &&
		(BaseClip.Id() == FName(TEXT("prone_front")) || BaseClip.Id() == FName(TEXT("prone_back")) ||
		 ((BaseClip.Id() == FName(TEXT("knockdown_front")) || BaseClip.Id() == FName(TEXT("knockdown_back"))) &&
		  BaseClip.Time >= BaseClip.Info->EventTime(OpNames::GroundImpact, BaseClip.Duration())));
	const bool bFaceUp = bProneFaceUp;
	Trace(FString::Printf(TEXT("DEATH requested during %s (hit from %s)"), *GetStateText(), bHitFromFront ? TEXT("front") : TEXT("behind")));
	InterruptForDisable(TEXT("death"));
	Hits.Reset();
	if (Flags.Contains(OpNames::Stasis))
	{
		SetFlag(OpNames::Stasis, false);   // releases the frozen pose and restores the movement mode
	}
	Flags.Reset();
	ChargeTime = -1.f;
	Char->StopDialogueAudio();
	if (bWasProne)
	{
		// already lying: go straight to the dead pose that matches the lying side
		return StartBase(bFaceUp ? TEXT("dead_front") : TEXT("dead_back"), EOpState::Dead, bFaceUp ? TEXT("front") : TEXT("back"), 0.35f);
	}
	// death_front = lethal hit from the front (ends face-up), death_back = from behind (ends face-down)
	return StartBase(bHitFromFront ? TEXT("death_front") : TEXT("death_back"), EOpState::Dead, bHitFromFront ? TEXT("front") : TEXT("back"), 0.12f);
}

bool UOperativeStateComponent::Respawn(const FVector& Location, float YawDeg)
{
	if (State != EOpState::Dead)
	{
		Refuse(TEXT("respawn"), TEXT("only from dead"));
		return false;
	}
	Char->SetActorLocation(Location, false, nullptr, ETeleportType::TeleportPhysics);
	SetActorYaw(YawDeg);
	if (Move)
	{
		Move->StopMovementImmediately();
		Move->ClearForcedVelocity();
		Move->SetMovementMode(MOVE_Walking);
	}
	Hits.Reset();
	Flags.Reset();
	UpperClip.Reset();
	UpperTag = NAME_None;
	Ammo = 12;
	bBeaconDeployed = false;
	bBeaconGrabbed = false;
	bWounded = false;
	ChargeTime = -1.f;
	bChannelEmitting = false;
	bHitWindow = false;
	RootYawOffset = 0.f;
	RecallDelay = -1.f;
	bResetSecondary = true;
	Char->SetMeshHiddenForBlink(false);
	Char->OnRespawned();
	Trace(TEXT("RESPAWN props, flags, ammo and layers reset"));
	return StartBase(TEXT("respawn"), EOpState::Respawn, NAME_None, 0.f);
}

void UOperativeStateComponent::SetFlag(FName Flag, bool bOn, const FVector& Source)
{
	if (State == EOpState::Dead)
	{
		return;
	}
	if (bOn == Flags.Contains(Flag))
	{
		return;
	}
	if (bOn)
	{
		Flags.Add(Flag);
		FlagSource = Source;
		Trace(FString::Printf(TEXT("FLAG %s on"), *Flag.ToString()));
		if (Flag == OpNames::Silence)
		{
			ChannelInterrupt(TEXT("silence"));
			ChargeCancel(TEXT("silence"));
			UplinkCancel(TEXT("silence"));
			if (UpperClip.IsValid() && UpperTag == OpNames::CastDir && UpperClip.Time < UpperClip.Info->EventTime(TEXT("cast_release"), 0.f))
			{
				ClearUpper(0.12f, TEXT("silenced before cast_release: no effect"));
			}
		}
		else if (Flag == OpNames::Disarm)
		{
			ChargeCancel(TEXT("disarm"));
		}
		else if (Flag == OpNames::Stasis)
		{
			if (Move)
			{
				SavedMovementModeFlag = Move->IsFalling() ? FName(TEXT("falling")) : FName(TEXT("walking"));
				Move->StopMovementImmediately();
				Move->ClearForcedVelocity();
				Move->DisableMovement();
			}
		}
		else if (Flag == OpNames::Fear || Flag == OpNames::Charm || Flag == OpNames::Taunt)
		{
			if (State == EOpState::Viewer)
			{
				ExitViewer();
			}
			ChannelInterrupt(TEXT("forced movement"));
			UplinkCancel(TEXT("forced movement"));
		}
	}
	else
	{
		Flags.Remove(Flag);
		Trace(FString::Printf(TEXT("FLAG %s off"), *Flag.ToString()));
		if (Flag == OpNames::Stasis && Move)
		{
			Move->SetMovementMode(SavedMovementModeFlag == FName(TEXT("falling")) ? MOVE_Falling : MOVE_Walking);
			Anim->Input.bFrozen = false;
		}
	}
}

bool UOperativeStateComponent::ViewClip(FName ClipId)
{
	const FMorphClip* Info = Data->Find(ClipId);
	if (!Info || State == EOpState::Dead)
	{
		return false;
	}
	if (State != EOpState::Viewer)
	{
		InterruptForDisable(TEXT("motion viewer"));
	}
	Hits.Reset();
	if (Move)
	{
		Move->StopMovementImmediately();
		Move->ClearForcedVelocity();
	}
	bViewerPaused = false;
	static const FName NAME_Additive(TEXT("additive"));
	if (Info->Layer == NAME_Additive)
	{
		// additive clips are shown as intended: layered over the combat idle and re-triggered
		if (!StartBase(TEXT("idle_combat"), EOpState::Viewer, ClipId, 0.2f))
		{
			return false;
		}
		AddHitInstance(ClipId, 1.f, true);
		Trace(FString::Printf(TEXT("VIEW additive %s layered over idle_combat (re-triggered every %.2f s)"), *ClipId.ToString(), Info->Duration + 0.6f));
		return true;
	}
	if (Info->bRootMotion)
	{
		Char->SetActorLocation(Char->ViewerLocation, false, nullptr, ETeleportType::TeleportPhysics);
		bResetSecondary = true;
	}
	return StartBase(ClipId, EOpState::Viewer, ClipId, 0.2f);
}

bool UOperativeStateComponent::ViewReferencePose()
{
	if (State == EOpState::Dead)
	{
		return false;
	}
	if (State != EOpState::Viewer)
	{
		InterruptForDisable(TEXT("motion viewer"));
	}
	Hits.Reset();
	if (Move)
	{
		Move->StopMovementImmediately();
		Move->ClearForcedVelocity();
	}
	BaseClip.Reset();
	SetState(EOpState::Viewer, TEXT("reference_pose"));
	Transition(0.2f);
	return true;
}

void UOperativeStateComponent::ViewerScrub(float NormalizedTime)
{
	if (State == EOpState::Viewer && BaseClip.IsValid())
	{
		BaseClip.Time = FMath::Clamp(NormalizedTime, 0.f, 1.f) * BaseClip.Duration();
		BaseClip.FiredUpTo = BaseClip.Time;
		BaseClip.bFinished = false;
		bViewerPaused = true;
	}
}

void UOperativeStateComponent::ExitViewer()
{
	if (State == EOpState::Viewer)
	{
		Hits.Reset();
		EnterLocomotion(0.25f);
	}
}

void UOperativeStateComponent::ClearFace()
{
	FaceDirect.Reset();
	FaceVisemes.Reset();
	FaceExpressions.Reset();
	FaceVisemesApplied.Reset();
	FaceExpressionsApplied.Reset();
	bManualGaze = false;
	GazeYawDeg = GazePitchDeg = 0.f;
}

void UOperativeStateComponent::ResetAll()
{
	if (State == EOpState::Dead)
	{
		Respawn(Char->SpawnLocation, Char->SpawnYaw);
	}
	InterruptForDisable(TEXT("reset"));
	if (Flags.Contains(OpNames::Stasis))
	{
		SetFlag(OpNames::Stasis, false);
	}
	Flags.Reset();
	Hits.Reset();
	UpperClip.Reset();
	UpperTag = NAME_None;
	Ammo = 12;
	bBeaconDeployed = false;
	bWounded = false;
	ClearFace();
	Char->SetActorLocation(Char->SpawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
	SetActorYaw(Char->SpawnYaw);
	if (Move)
	{
		Move->StopMovementImmediately();
		Move->SetMovementMode(MOVE_Walking);
	}
	bResetSecondary = true;
	Char->OnRespawned();
	EnterLocomotion(0.f);
	Trace(TEXT("RESET character returned to the spawn point in a clean living state"));
}

void UOperativeStateComponent::NotifyLanded(float ImpactSpeed)
{
	if (State == EOpState::Knockup)
	{
		bProneFaceUp = true;
		const FMorphClip* Info = Data->Find(TEXT("knockdown_back"));
		const float T = Info ? Info->EventTime(OpNames::GroundImpact, 0.f) : 0.f;
		Trace(FString::Printf(TEXT("LANDED from knock-up at %.0f cm/s -> knockdown_back from ground_impact"), ImpactSpeed));
		StartBase(TEXT("knockdown_back"), EOpState::Knockdown, NAME_None, 0.12f, T);
		return;
	}
	if (State != EOpState::Air || Tag == OpNames::Land)
	{
		return;
	}
	const bool bHeavy = ImpactSpeed >= 900.f;
	Trace(FString::Printf(TEXT("LANDED at %.0f cm/s -> %s"), ImpactSpeed, bHeavy ? TEXT("land_heavy") : TEXT("jump_land")));
	FallTime = 0.f;
	StartBase(bHeavy ? TEXT("land_heavy") : TEXT("jump_land"), EOpState::Air, OpNames::Land, 0.08f);
}

// ================================================================================================ movement / facing
void UOperativeStateComponent::UpdateMovement(float Dt)
{
	if (!Move)
	{
		return;
	}
	const bool bForcedMove = Flags.Contains(OpNames::Fear) || Flags.Contains(OpNames::Charm) || Flags.Contains(OpNames::Taunt);
	FVector Dir = Input.MoveDir.GetClampedToMaxSize(1.0);
	Dir.Z = 0.0;
	bool bSprint = Input.bSprint;
	if (bForcedMove)
	{
		FVector To = FlagSource - Char->GetActorLocation();
		To.Z = 0.0;
		const double Dist = To.Size();
		To = To.GetSafeNormal();
		if (Flags.Contains(OpNames::Fear))
		{
			Dir = -To;
		}
		else
		{
			Dir = Dist > 160.0 ? To : FVector::ZeroVector;
		}
		bSprint = false;
	}

	// which states may translate
	bool bMayMove = false;
	float SpeedCap = Data->RunSpeed;
	if (State == EOpState::Locomotion)
	{
		bMayMove = !(BaseClip.IsValid() && Tag == OpNames::Turn);
	}
	else if (State == EOpState::Air)
	{
		bMayMove = Tag != OpNames::Jump || bJumpLaunched;
	}
	if (Flags.Contains(OpNames::Root))
	{
		bMayMove = false;
	}
	const bool bSlowUpper = UpperClip.IsValid() && (UpperTag == OpNames::Reload || UpperTag == OpNames::Charge);
	const bool bForward = Dir.IsNearlyZero() ? true : FMath::Abs(LocalDirDeg(Dir)) < 30.f;
	SprintBlend = 0.f;
	if (Input.bWalk || bWounded || bSlowUpper)
	{
		SpeedCap = Data->WalkSpeed;
	}
	else if (bSprint && bForward && !Input.bAim)
	{
		SpeedCap = Data->SprintSpeed;
		SprintBlend = 1.f;
	}
	if (Input.SpeedOverride >= 0.f)
	{
		SpeedCap = FMath::Min(Input.SpeedOverride, bWounded || bSlowUpper ? Data->WalkSpeed : (bForward ? Data->SprintSpeed : Data->RunSpeed));
		SprintBlend = SpeedCap > Data->RunSpeed + 1.f ? 1.f : 0.f;
	}
	Move->MaxWalkSpeed = SpeedCap;
	// start / stop / pivot clips with an authored speed profile drive the capsule so that the feet cannot slide
	const bool bProfile = State == EOpState::Locomotion && BaseClip.IsValid() && !BaseClip.bFinished && BaseClip.Info->SpeedProfile.Num() > 1 &&
		(Tag == OpNames::Start || Tag == OpNames::Stop || Tag == OpNames::Pivot) && IsGrounded() && !Flags.Contains(OpNames::Stasis);
	const bool bForcedVel = (State == EOpState::Action && Tag == OpNames::Dash) || State == EOpState::Knockback ||
		(State == EOpState::Viewer && BaseClip.IsValid() && BaseClip.Info->bRootMotion) || bProfile;
	if (!bForcedVel)
	{
		Move->ClearForcedVelocity();
	}
	if (bProfile)
	{
		if (TracedProfileActivation != BaseClip.ActivationId)
		{
			TracedProfileActivation = BaseClip.ActivationId;
			Trace(FString::Printf(TEXT("PROFILE %s #%d: the capsule follows the authored speed profile (%d frames, %.0f -> %.0f cm/s, scale %.2f)"), *BaseClip.Id().ToString(),
				BaseClip.ActivationId, BaseClip.Info->SpeedProfile.Num() - 1, BaseClip.Info->SpeedProfile[0], BaseClip.Info->SpeedProfile.Last(), ProfileScale));
		}
		if (Tag == OpNames::Start && bMayMove && !Dir.IsNearlyZero())
		{
			ProfileDir = Dir.GetSafeNormal2D();   // steering stays possible while starting
		}
		const TArray<float>& Prof = BaseClip.Info->SpeedProfile;
		const float F = FMath::Clamp(BaseClip.Time * Data->Fps, 0.f, (float)(Prof.Num() - 1));
		const int32 I0 = FMath::FloorToInt(F);
		const int32 I1 = FMath::Min(I0 + 1, Prof.Num() - 1);
		const float V = FMath::Lerp(Prof[I0], Prof[I1], F - (float)I0) * ProfileScale;
		Move->SetForcedVelocity(ProfileDir * V);
	}
	if (bMayMove && !Dir.IsNearlyZero())
	{
		Char->AddMovementInput(Dir, 1.f);
	}

	// ---- measured motion
	FVector Vel = Move->Velocity;
	Vel.Z = 0.0;
	Speed = (float)Vel.Size();
	const bool bMoving = Speed > 12.f;
	if (bMoving)
	{
		TravelDir = LocalDirDeg(Vel.GetSafeNormal());
		TimeMoving += Dt;
	}
	else
	{
		TimeMoving = 0.f;
	}

	// ---- facing
	const bool bFreeFacing = (State == EOpState::Locomotion && (!BaseClip.IsValid() || Tag == OpNames::Start)) || State == EOpState::Air;
	const bool bUseStrafe = bStrafe || Input.bAim || UpperClip.IsValid();
	float CurYaw = (float)Char->GetActorRotation().Yaw;
	if (bFreeFacing && !Flags.Contains(OpNames::Stasis))
	{
		if (bForcedMove)
		{
			if (!Dir.IsNearlyZero())
			{
				CurYaw = FMath::FixedTurn(CurYaw, (float)Dir.Rotation().Yaw, 540.f * Dt);
				SetActorYaw(CurYaw);
			}
			else
			{
				FVector To = FlagSource - Char->GetActorLocation();
				CurYaw = FMath::FixedTurn(CurYaw, (float)To.Rotation().Yaw, 360.f * Dt);
				SetActorYaw(CurYaw);
			}
		}
		else if (bUseStrafe)
		{
			if (Input.bHasAimPoint)
			{
				FVector To = Input.AimPoint - Char->GetActorLocation();
				To.Z = 0.0;
				if (To.SizeSquared() > 100.0)
				{
					const float Want = (float)To.Rotation().Yaw;
					const float Delta = FRotator::NormalizeAxis(Want - CurYaw);
					// debounce: the aim must stay outside the +-60 deg aim range for a moment before a turn starts
					TurnHoldTime = (FMath::Abs(Delta) > 60.f && !bMoving) ? TurnHoldTime + Dt : 0.f;
					if (bMoving || State == EOpState::Air)
					{
						SetActorYaw(FMath::FixedTurn(CurYaw, Want, 420.f * Dt));
					}
					else if (FMath::Abs(Delta) > 60.f && State == EOpState::Locomotion && IsGrounded() && TurnHoldTime >= 0.12f)
					{
						Trace(FString::Printf(TEXT("TURN in place: aim is %.0f deg to the %s of the facing"), FMath::Abs(Delta), Delta < 0.f ? TEXT("left") : TEXT("right")));
						DoTurn(Delta < 0.f ? 90.f : -90.f);   // Unreal yaw delta < 0 = turn to the character's left
					}
				}
			}
		}
		else if (bMoving && !Dir.IsNearlyZero())
		{
			// travel mode: face the travel direction
			const float Want = (float)Dir.Rotation().Yaw;
			const float Delta = FRotator::NormalizeAxis(Want - CurYaw);
			if (FMath::Abs(Delta) > 135.f && Speed > 300.f && State == EOpState::Locomotion && IsGrounded() && !UpperClip.IsValid())
			{
				const bool bLeft = Delta < 0.f;
				const FMorphClip* Info = Data->Find(bLeft ? TEXT("pivot_l180") : TEXT("pivot_r180"));
				if (Info)
				{
					Trace(FString::Printf(TEXT("PIVOT: travel input reversed by %.0f deg at %.0f cm/s (facing %.0f, wanted %.0f)"), Delta, Speed, CurYaw, Want));
					SetActorYaw(CurYaw - Info->TurnYawDeg);
					RootYawOffset = Info->TurnYawDeg;
					ProfileDir = Vel.GetSafeNormal2D();   // the profile runs along the old travel direction and ends reversed
					ProfileScale = Info->SpeedProfile.Num() > 1 ? FMath::Clamp(Speed / FMath::Max(FMath::Abs(Info->SpeedProfile[0]), 1.f), 0.5f, 1.6f) : 1.f;
					StartBase(Info->Id, EOpState::Locomotion, OpNames::Pivot, 0.1f);
				}
			}
			else
			{
				SetActorYaw(FMath::FixedTurn(CurYaw, Want, 540.f * Dt));
			}
		}
		else if (!Dir.IsNearlyZero() && State == EOpState::Locomotion)
		{
			SetActorYaw(FMath::FixedTurn(CurYaw, (float)Dir.Rotation().Yaw, 540.f * Dt));
		}
	}

	// ---- travel mode starts and stops
	if (State == EOpState::Locomotion && BaseClip.IsValid() && Tag == OpNames::Stop && bMayMove && !Dir.IsNearlyZero())
	{
		Trace(TEXT("STOP cancelled by new travel input"));
		EnterLocomotion(0.15f);
	}
	if (!bUseStrafe && State == EOpState::Locomotion && !BaseClip.IsValid() && IsGrounded() && !UpperClip.IsValid() && !bForcedMove)
	{
		const bool bWantMove = bMayMove && !Dir.IsNearlyZero();
		if (bWantMove && !bWasMoving && Speed < 40.f && SpeedCap > Data->WalkSpeed + 1.f)
		{
			ProfileDir = Dir.GetSafeNormal2D();
			ProfileScale = 1.f;
			StartBase(TEXT("start_f"), EOpState::Locomotion, OpNames::Start, 0.1f);
		}
		else if (!bWantMove && bWasMoving && Speed > 280.f)
		{
			const FMorphClip* StopInfo = Data->Find(TEXT("stop_f"));
			ProfileDir = Vel.GetSafeNormal2D();
			ProfileScale = (StopInfo && StopInfo->SpeedProfile.Num() > 1) ? FMath::Clamp(Speed / FMath::Max(FMath::Abs(StopInfo->SpeedProfile[0]), 1.f), 0.5f, 1.6f) : 1.f;
			StartBase(TEXT("stop_f"), EOpState::Locomotion, OpNames::Stop, 0.12f);
		}
		bWasMoving = bWantMove;
	}
	else if (State != EOpState::Locomotion || bUseStrafe)
	{
		bWasMoving = bMayMove && !Dir.IsNearlyZero();
	}
	LastMoveDir = Dir;
}

// ================================================================================================ gait blend
void UOperativeStateComponent::UpdateLocomotionBlend(float Dt)
{
	LocoSamples.Reset();
	if (!Anim)
	{
		return;
	}
	// idle variant
	const FName WantIdle = bWounded ? FName(TEXT("idle_wounded")) : ((CombatTimer > 0.f || Input.bAim) ? FName(TEXT("idle_combat")) : FName(TEXT("idle_relaxed")));
	if (WantIdle != IdleClip)
	{
		IdleClip = WantIdle;
		Trace(FString::Printf(TEXT("IDLE %s"), *IdleClip.ToString()));
		if (State == EOpState::Locomotion && !BaseClip.IsValid())
		{
			Transition(0.35f);
		}
	}
	const FMorphClip* IdleInfo = Data->Find(IdleClip);
	IdleTime += Dt;
	if (IdleInfo && IdleTime >= IdleInfo->Duration)
	{
		IdleTime = FMath::Fmod(IdleTime, FMath::Max(IdleInfo->Duration, 0.01f));
	}
	WoundedAlpha = FMath::FInterpTo(WoundedAlpha, bWounded ? 0.6f : 0.f, Dt, 4.f);

	if (Walk.Clips.Num() < 2 || Run.Clips.Num() < 2)
	{
		return;
	}
	const float S = Speed;
	const float WalkV = Walk.Speed, RunV = Run.Speed, SprintV = SprintClip ? SprintClip->NominalSpeed : RunV;
	float WIdle = 1.f - FMath::Clamp(S / WalkV, 0.f, 1.f);
	float WWalk = 0.f, WRun = 0.f, WSprint = 0.f;
	if (S <= WalkV)
	{
		WWalk = 1.f - WIdle;
	}
	else if (S <= RunV)
	{
		WRun = (S - WalkV) / FMath::Max(RunV - WalkV, 1.f);
		WWalk = 1.f - WRun;
	}
	else
	{
		const bool bSprintOk = SprintClip && FMath::Abs(TravelDir) < 30.f && SprintBlend > 0.5f;
		WSprint = bSprintOk ? FMath::Clamp((S - RunV) / FMath::Max(SprintV - RunV, 1.f), 0.f, 1.f) : 0.f;
		WRun = 1.f - WSprint;
	}
	// shared phase; foot speed follows the controller speed
	const float MoveW = WWalk + WRun + WSprint;
	if (MoveW > 1.e-3f)
	{
		// cycle length and nominal speed of the clips that are actually blended (directions may differ in frame count)
		auto PairValue = [&](const FGaitSet& Set, bool bDuration, float Fallback)
		{
			const int32 N = Set.Clips.Num();
			const float A = FRotator::ClampAxis(TravelDir) / (360.f / N);
			const int32 I0 = FMath::FloorToInt(A) % N;
			const int32 I1 = (I0 + 1) % N;
			const float F = A - FMath::FloorToFloat(A);
			const float V0 = bDuration ? Set.Clips[I0]->Duration : Set.Clips[I0]->NominalSpeed;
			const float V1 = bDuration ? Set.Clips[I1]->Duration : Set.Clips[I1]->NominalSpeed;
			const float R = FMath::Lerp(V0, V1, F);
			return R > 1.e-3f ? R : Fallback;
		};
		const float T = (WWalk * PairValue(Walk, true, Walk.Duration) + WRun * PairValue(Run, true, Run.Duration) + WSprint * (SprintClip ? SprintClip->Duration : Run.Duration)) / MoveW;
		const float V = (WWalk * PairValue(Walk, false, WalkV) + WRun * PairValue(Run, false, RunV) + WSprint * SprintV) / MoveW;
		LocoRate = FMath::Clamp(S / FMath::Max(V, 1.f), 0.5f, 1.5f);
		const float PrevPhase = Phase;
		const bool bLocoActive = State == EOpState::Locomotion && !BaseClip.IsValid();
		Phase += Dt * LocoRate / FMath::Max(T, 0.05f);
		const bool bWrapped = Phase >= 1.f;
		if (bWrapped)
		{
			Phase = FMath::Fmod(Phase, 1.f);
		}
		// direction pair
		auto AddPair = [&](const FGaitSet& Set, float W, const FMorphClip*& OutDominant, float& OutBest)
		{
			if (W <= 1.e-3f)
			{
				return;
			}
			const int32 N = Set.Clips.Num();
			const float Step = 360.f / N;
			const float A = FRotator::ClampAxis(TravelDir) / Step;
			const int32 I0 = FMath::FloorToInt(A) % N;
			const int32 I1 = (I0 + 1) % N;
			const float F = A - FMath::FloorToFloat(A);
			const FMorphClip* C0 = Set.Clips[I0];
			const FMorphClip* C1 = Set.Clips[I1];
			LocoSamples.Add({ Anim->GetSequence(C0->Id), Phase * C0->Duration, W * (1.f - F), true });
			LocoSamples.Add({ Anim->GetSequence(C1->Id), Phase * C1->Duration, W * F, true });
			if (W * (1.f - F) > OutBest)
			{
				OutBest = W * (1.f - F);
				OutDominant = C0;
			}
			if (W * F > OutBest)
			{
				OutBest = W * F;
				OutDominant = C1;
			}
		};
		const FMorphClip* Dominant = nullptr;
		float Best = 0.f;
		AddPair(Walk, WWalk, Dominant, Best);
		AddPair(Run, WRun, Dominant, Best);
		if (WSprint > 1.e-3f && SprintClip)
		{
			LocoSamples.Add({ Anim->GetSequence(SprintClip->Id), Phase * SprintClip->Duration, WSprint, true });
			if (WSprint > Best)
			{
				Dominant = SprintClip;
			}
		}
		DominantClip = Dominant ? Dominant->Id : NAME_None;
		if (bLocoActive && DominantClip != TracedGait && !DominantClip.IsNone())
		{
			TracedGait = DominantClip;
			Trace(FString::Printf(TEXT("GAIT %s (dominant; speed %.0f cm/s, travel dir %+.0f deg, rate %.2fx)"), *DominantClip.ToString(), S, TravelDir, LocoRate));
		}
		// foot contact markers of the dominant clip only, on the shared phase
		if (Dominant && bLocoActive && PrevPhase != Phase)
		{
			for (const FMorphEvent& E : Dominant->Events)
			{
				const float N = E.Normalized;
				const bool bCross = bWrapped ? (N > PrevPhase || N <= Phase) : (N > PrevPhase && N <= Phase);
				if (bCross)
				{
					FOpClipPlay Tmp;
					Tmp.Info = Dominant;
					Tmp.Seq = Anim->GetSequence(Dominant->Id);
					Tmp.Time = Phase * Dominant->Duration;
					Tmp.ActivationId = 0;
					Fire(Tmp, E);
				}
			}
		}
	}
	else
	{
		Phase = 0.f;
		LocoRate = 1.f;
		DominantClip = NAME_None;
		TracedGait = NAME_None;
	}
	if (WIdle > 1.e-3f && IdleInfo)
	{
		LocoSamples.Add({ Anim->GetSequence(IdleClip), IdleTime, WIdle, true });
	}
}

// ================================================================================================ aim / look
void UOperativeStateComponent::UpdateAim(float Dt)
{
	const bool bAimState = State == EOpState::Locomotion || State == EOpState::Air;
	const bool bAimAction = UpperClip.IsValid() && (UpperTag == OpNames::Ranged || UpperTag == OpNames::CastDir || UpperTag == OpNames::Charge);
	const bool bWantAim = bAimState && !(BaseClip.IsValid() && State == EOpState::Locomotion && Tag != OpNames::Turn) &&
		UpperTag != OpNames::Reload && (Input.bAim || AimHold > 0.f || bAimAction);
	// one AimWeight for both aim steps (centre pose blend + mesh-space additive), 0.15 s linear blend
	AimAlpha = FMath::FInterpConstantTo(AimAlpha, bWantAim ? 1.f : 0.f, Dt, 1.f / 0.15f);
	float WantYaw = 0.f, WantPitch = 0.f;
	FVector Attention = Char->GetActorLocation() + Char->GetActorForwardVector() * 400.0 + FVector(0, 0, 65);
	if (Input.bHasAimPoint)
	{
		Attention = Input.AimPoint;
		const FVector Origin = Char->GetMesh()->GetSocketLocation(TEXT("spine_03"));
		const FVector To = Input.AimPoint - Origin;
		// while a turn clip compensates the actor yaw, measure against the visual facing
		WantYaw = FMath::Clamp(LocalDirDeg(To.GetSafeNormal2D()), -60.f, 60.f);
		WantPitch = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2((float)To.Z, (float)To.Size2D())), -35.f, 35.f);
	}
	if (Flags.Contains(OpNames::Fear) || Flags.Contains(OpNames::Charm) || Flags.Contains(OpNames::Taunt))
	{
		Attention = FlagSource + FVector(0, 0, 150);
	}
	if (bLookAtCamera)
	{
		Attention = CameraLocation;
	}
	AimYaw = FMath::FInterpTo(AimYaw, WantYaw, Dt, 12.f);
	AimPitch = FMath::FInterpTo(AimPitch, WantPitch, Dt, 12.f);
	if (AimAlpha > 0.95f)
	{
		// trace which calibrated grid sample the aim layer is closest to
		static const FName NAME_AimLayer(TEXT("aim"));
		const FMorphClip* Best = nullptr;
		float BestD = 1.e9f;
		for (const FMorphClip& Clip : Data->Clips)
		{
			if (Clip.Layer == NAME_AimLayer)
			{
				const float D2 = FMath::Square(Clip.AimYawDeg - AimYaw) + FMath::Square(Clip.AimPitchDeg - AimPitch);
				if (D2 < BestD)
				{
					BestD = D2;
					Best = &Clip;
				}
			}
		}
		if (Best && BestD < FMath::Square(9.f) && Best->Id != TracedAimPose)
		{
			TracedAimPose = Best->Id;
			Trace(FString::Printf(TEXT("AIM pose %s reached (yaw %+.0f pitch %+.0f, layer weight %.2f)"), *Best->Id.ToString(), AimYaw, AimPitch, AimAlpha));
		}
	}
	else if (AimAlpha < 0.05f)
	{
		TracedAimPose = NAME_None;
	}
	LookTargetWorld = FMath::VInterpTo(LookTargetWorld, Attention, Dt, 10.f);
	const bool bLookState = bLookAt && (State == EOpState::Locomotion || State == EOpState::Air) && !(BaseClip.IsValid() && State == EOpState::Locomotion && Tag == OpNames::Turn);
	LookAlpha = FMath::FInterpTo(LookAlpha, bLookState ? 1.f : 0.f, Dt, 6.f);
	const bool bEyes = bManualGaze || bLookState || (bLookAt && bLookAtCamera && State != EOpState::Dead && State != EOpState::Sleep && State != EOpState::Stun && State != EOpState::Knockdown);
	EyeAlpha = FMath::FInterpTo(EyeAlpha, bEyes ? 1.f : 0.f, Dt, 8.f);
}

void UOperativeStateComponent::UpdateHits(float Dt)
{
	for (int32 i = Hits.Num() - 1; i >= 0; --i)
	{
		FOpHitInstance& H = Hits[i];
		H.Time += Dt * (H.bLoopForViewer ? (bViewerPaused ? 0.f : ViewerRate) : 1.f);
		if (H.Time >= H.Info->Duration)
		{
			if (H.bLoopForViewer && State == EOpState::Viewer)
			{
				if (H.Time >= H.Info->Duration + 0.6f)
				{
					H.Time = 0.f;
				}
			}
			else
			{
				Hits.RemoveAt(i);
			}
		}
	}
}

// ================================================================================================ face
void UOperativeStateComponent::UpdateFace(float Dt)
{
	// automatic expression from the state
	FName Want;
	float WantW = 0.f;
	switch (State)
	{
	case EOpState::Stun: Want = TEXT("pain"); WantW = 0.7f; break;
	case EOpState::Knockback:
	case EOpState::Knockup:
	case EOpState::Knockdown: Want = TEXT("pain"); WantW = 0.8f; break;
	default: break;
	}
	if (Flags.Contains(OpNames::Fear)) { Want = TEXT("surprise"); WantW = 0.8f; }
	else if (Flags.Contains(OpNames::Charm)) { Want = TEXT("joy"); WantW = 0.8f; }
	else if (Flags.Contains(OpNames::Taunt)) { Want = TEXT("anger"); WantW = 0.9f; }
	if (PainPulse > 0.f && Want.IsNone())
	{
		Want = TEXT("pain");
		WantW = FMath::Clamp(PainPulse, 0.f, 1.f) * 0.8f;
	}
	if (bWounded && Want.IsNone() && State != EOpState::Dead)
	{
		Want = TEXT("pain");
		WantW = 0.3f;
	}
	// (no automatic preset for actions: their clips carry the authored face animation)
	if (Want != AutoExpressionTarget)
	{
		if (AutoExpressionWeight <= 0.02f || Want == AutoExpression)
		{
			AutoExpression = Want;
			AutoExpressionTarget = Want;
		}
		else
		{
			WantW = 0.f;   // fade the old one out first
		}
	}
	if (AutoExpression.IsNone())
	{
		WantW = 0.f;
	}
	else if (AutoExpression != Want)
	{
		WantW = 0.f;
	}
	AutoExpressionWeight = FMath::FInterpTo(AutoExpressionWeight, WantW, Dt, 9.f);
	if (AutoExpressionWeight <= 0.02f && AutoExpression != Want)
	{
		AutoExpression = Want;
		AutoExpressionTarget = Want;
	}

	// preset weights follow their targets quickly but without popping
	auto Follow = [Dt](const TMap<FName, float>& Target, TMap<FName, float>& Applied, float Speed)
	{
		for (const TPair<FName, float>& KV : Target)
		{
			float& V = Applied.FindOrAdd(KV.Key);
			V = FMath::FInterpTo(V, KV.Value, Dt, Speed);
		}
		for (TPair<FName, float>& KV : Applied)
		{
			if (!Target.Contains(KV.Key))
			{
				KV.Value = FMath::FInterpTo(KV.Value, 0.f, Dt, Speed);
			}
		}
	};
	Follow(FaceVisemes, FaceVisemesApplied, 22.f);
	Follow(FaceExpressions, FaceExpressionsApplied, 12.f);

	// automatic blink
	const bool bBlinkAllowed = bAutoBlink && (State == EOpState::Locomotion || State == EOpState::Air || State == EOpState::Action);
	if (BlinkPhase >= 0.f)
	{
		BlinkPhase += Dt / 0.2f;
		if (BlinkPhase >= 1.f)
		{
			BlinkPhase = -1.f;
			BlinkTimer = 2.2f + Random.FRand() * 3.2f;
		}
	}
	else if (bBlinkAllowed)
	{
		BlinkTimer -= Dt;
		if (BlinkTimer <= 0.f)
		{
			BlinkPhase = 0.f;
		}
	}
}

// ================================================================================================ ground adaptation
void UOperativeStateComponent::UpdateFootIK(float Dt)
{
	const bool bActive = bFootIK && State == EOpState::Locomotion && IsGrounded();
	FootIKAlpha = FMath::FInterpTo(FootIKAlpha, bActive ? 1.f : 0.f, Dt, 8.f);
	float Target[2] = { 0.f, 0.f };
	FVector Normal[2] = { FVector::UpVector, FVector::UpVector };
	FootClearance[0] = FootClearance[1] = -1.f;
	if (State == EOpState::Locomotion && IsGrounded())
	{
		USkeletalMeshComponent* Mesh = Char->GetMesh();
		// the mesh origin is the authored ground plane of the character
		const double BaseZ = Mesh->GetComponentLocation().Z;
		static const FName FootBones[2] = { FName(TEXT("foot_l")), FName(TEXT("foot_r")) };
		FCollisionQueryParams Q(SCENE_QUERY_STAT(OperativeFootIK), false, Char);
		FCollisionObjectQueryParams Obj;
		Obj.AddObjectTypesToQuery(ECC_WorldStatic);
		Obj.AddObjectTypesToQuery(ECC_WorldDynamic);
		for (int32 s = 0; s < 2; ++s)
		{
			const FVector P = Mesh->GetSocketLocation(FootBones[s]);
			FHitResult Hit;
			if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(P.X, P.Y, BaseZ + 60.0), FVector(P.X, P.Y, BaseZ - 60.0), Obj, Q))
			{
				FootClearance[s] = (float)(P.Z - Hit.ImpactPoint.Z);
				if (bActive)
				{
					Target[s] = FMath::Clamp((float)(Hit.ImpactPoint.Z - BaseZ), -25.f, 25.f);
					if (Hit.ImpactNormal.Z > 0.7)
					{
						Normal[s] = Hit.ImpactNormal;
					}
				}
			}
		}
	}
	const float PelvisTarget = FMath::Min3(0.f, Target[0], Target[1]);
	PelvisOffset = FMath::FInterpTo(PelvisOffset, PelvisTarget, Dt, 9.f);
	for (int32 s = 0; s < 2; ++s)
	{
		FootOffset[s] = FMath::FInterpTo(FootOffset[s], Target[s], Dt, 14.f);
		FootNormal[s] = FMath::VInterpTo(FootNormal[s], Normal[s], Dt, 10.f).GetSafeNormal();
	}
}

// ================================================================================================ output for the animation worker
void UOperativeStateComponent::AddPropAttachments(const FOpClipPlay& Play, int32 Source, FOperativeAnimInput& Out) const
{
	if (!Play.IsValid())
	{
		return;
	}
	for (const FMorphPropSegment& Seg : Play.Info->PropSegments)
	{
		if (Play.Time >= Seg.Start && Play.Time <= Seg.End)
		{
			FOpPropAttach A;
			A.Prop = Seg.Prop;
			A.Holder = Seg.Holder;
			A.Source = Source;
			A.Weight = 1.f;
			Out.PropAttach.Add(A);
		}
	}
}

void UOperativeStateComponent::BuildAnimInput(float Dt)
{
	FOperativeAnimInput& Out = Anim->Input;
	Out.FrameSerial = FrameSerial;
	Out.DeltaTime = Dt;
	Out.bFrozen = false;
	Out.Base.Reset();
	if (BaseClip.IsValid())
	{
		Out.Base.Add({ BaseClip.Seq, BaseClip.Time, 1.f, BaseClip.bLoop });
	}
	else if (State != EOpState::Viewer)
	{
		Out.Base = LocoSamples;
	}
	// (viewer without a clip = reference pose: an empty base evaluates to the bind pose)
	Out.TransitionSerial = TransitionSerial;
	Out.TransitionTime = TransitionTime;
	Out.RootYawOffsetDeg = RootYawOffset;

	Out.Overlay = FOpClipSample();
	Out.OverlayAlpha = 0.f;
	if (WoundedAlpha > 0.01f && State == EOpState::Locomotion && !BaseClip.IsValid() && Speed > 20.f)
	{
		Out.Overlay = { Anim->GetSequence(TEXT("idle_wounded")), IdleTime, 1.f, true };
		Out.OverlayAlpha = WoundedAlpha * FMath::Clamp(Speed / Data->WalkSpeed, 0.f, 1.f);
	}

	Out.Upper.Reset();
	Out.UpperAlpha = 0.f;
	// clips that plant hands, knees or the body on the floor are played untouched: no upper-body, aim or additive hit layer
	const bool bFloorClip = BaseClip.IsValid() && BaseClip.Info->bFloorContact;
	AdditiveGate = FMath::FInterpConstantTo(AdditiveGate, bFloorClip ? 0.f : 1.f, Dt, 1.f / 0.12f);
	const bool bUpperAllowed = (State == EOpState::Locomotion || State == EOpState::Air) && !bFloorClip;
	if (UpperClip.IsValid() && bUpperAllowed)
	{
		Out.Upper.Add({ UpperClip.Seq, UpperClip.Time, 1.f, UpperClip.bLoop });
		Out.UpperAlpha = 1.f;
	}
	else if (AimAlpha > 0.01f && bUpperAllowed)
	{
		// aim stance: the calibrated centre pose carries the arms, the aim layer adds the direction
		Out.Upper.Add({ Anim->GetSequence(TEXT("aim_level_center")), 0.f, 1.f, false });
		Out.UpperAlpha = AimAlpha;
	}
	Out.AimYawDeg = AimYaw;
	Out.AimPitchDeg = AimPitch;
	Out.AimAlpha = bUpperAllowed ? AimAlpha : 0.f;

	Out.Hits.Reset();
	for (const FOpHitInstance& H : Hits)
	{
		if (H.Time <= H.Info->Duration && AdditiveGate > 0.01f)
		{
			Out.Hits.Add({ H.Seq, H.Time, H.Weight * AdditiveGate });
		}
	}

	const FTransform C2W = Char->GetMesh()->GetComponentTransform();
	Out.LookTargetCS = C2W.InverseTransformPosition(LookTargetWorld);
	Out.LookAlpha = LookAlpha;
	Out.EyeLookAlpha = EyeAlpha;
	if (bManualGaze)
	{
		// manual gaze from the face panel: a point 2 m in front of the head, offset by the slider angles
		const FVector Head = C2W.InverseTransformPosition(Char->GetMesh()->GetSocketLocation(TEXT("head")));
		const float Y = FMath::DegreesToRadians(GazeYawDeg), P = FMath::DegreesToRadians(GazePitchDeg);
		const FVector Fwd = C2W.InverseTransformVectorNoScale(Char->GetMesh()->GetSocketQuaternion(TEXT("head")).RotateVector(Char->HeadForwardLocal));
		const FVector Up(0, 0, 1);
		const FVector Left = FVector::CrossProduct(Fwd, Up).GetSafeNormal() * -1.0;
		Out.LookTargetCS = Head + (Fwd * FMath::Cos(Y) * FMath::Cos(P) + Left * FMath::Sin(Y) * FMath::Cos(P) + Up * FMath::Sin(P)) * 200.0;
		Out.LookAlpha = 0.f;
		Out.EyeLookAlpha = 1.f;
	}

	for (int32 s = 0; s < 2; ++s)
	{
		Out.FootOffsetZ[s] = FootOffset[s];
		Out.FootNormalCS[s] = C2W.InverseTransformVectorNoScale(FootNormal[s]);
	}
	Out.PelvisOffsetZ = PelvisOffset;
	Out.FootIKAlpha = FootIKAlpha;

	// ---- face control layer -> per channel totals
	TMap<FName, float> Totals = FaceDirect;
	auto Accumulate = [&](const TMap<FName, TMap<FName, float>>& Table, FName Name, float W)
	{
		if (W <= 0.f)
		{
			return;
		}
		if (const TMap<FName, float>* Map = Table.Find(Name))
		{
			for (const TPair<FName, float>& KV : *Map)
			{
				Totals.FindOrAdd(KV.Key) += KV.Value * W;
			}
		}
	};
	for (const TPair<FName, float>& KV : FaceVisemesApplied)
	{
		Accumulate(Data->Visemes, KV.Key, KV.Value);
	}
	for (const TPair<FName, float>& KV : FaceExpressionsApplied)
	{
		Accumulate(Data->Expressions, KV.Key, KV.Value);
	}
	if (!AutoExpression.IsNone())
	{
		Accumulate(Data->Expressions, AutoExpression, AutoExpressionWeight);
	}
	if (BlinkPhase >= 0.f)
	{
		const float B = FMath::Sin(BlinkPhase * PI);
		Totals.FindOrAdd(TEXT("blink_l")) += B;
		Totals.FindOrAdd(TEXT("blink_r")) += B;
	}
	if (State == EOpState::Sleep || State == EOpState::Dead)
	{
		Totals.FindOrAdd(TEXT("blink_l")) += 1.f;
		Totals.FindOrAdd(TEXT("blink_r")) += 1.f;
		if (State == EOpState::Dead)
		{
			Totals.FindOrAdd(TEXT("jaw_open")) += 0.18f;
		}
	}
	Out.MorphAdd.Reset();
	Out.FaceBones.Reset();
	for (const TPair<FName, float>& KV : Totals)
	{
		const float V = FMath::Clamp(KV.Value, 0.f, 1.f);
		if (V <= 1.e-4f)
		{
			continue;
		}
		if (Data->Morphs.Contains(KV.Key))
		{
			Out.MorphAdd.Emplace(KV.Key, V);
		}
		if (const TArray<FMorphBoneOffset>* Offsets = Data->BoneControls.Find(KV.Key))
		{
			for (const FMorphBoneOffset& O : *Offsets)
			{
				FOpFaceBone FB;
				FB.Bone = O.Bone;
				FB.bRotation = O.bRotation;
				FB.Quat = O.Quat;
				FB.Loc = O.Loc;
				FB.Value = V;
				Out.FaceBones.Add(FB);
			}
		}
	}

	// ---- props
	Out.PropAttach.Reset();
	AddPropAttachments(BaseClip, 0, Out);
	if (bUpperAllowed)
	{
		AddPropAttachments(UpperClip, 1, Out);
	}
	Out.HiddenBones.Reset();
	if (bBeaconDeployed)
	{
		Out.HiddenBones.Add(TEXT("prop_beacon"));
	}
	Out.bResetSecondary = bResetSecondary;
	bResetSecondary = false;
	Out.bSimulateSecondary = bSimulateSecondary;
	Out.bProceduralBones = bProceduralBones;
}
