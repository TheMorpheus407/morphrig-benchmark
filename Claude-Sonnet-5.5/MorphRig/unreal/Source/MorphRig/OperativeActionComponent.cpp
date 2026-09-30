#include "OperativeActionComponent.h"
#include "OperativeLibrary.h"
#include "OperativeCharacter.h"
#include "OperativeFaceComponent.h"
#include "Animation/AnimSequence.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/SkeletalMeshComponent.h"

// ------------------------------------------------------------------------------------------------ fallback event table
// Used only when a manifest clip has no event of that name (the manifest is authoritative). Every synthetic event is marked
// source=fallback in the trace and drawn yellow in the marker timeline, so nobody mistakes it for authored data.

namespace
{
	struct FFallbackEvent
	{
		const TCHAR* ClipPattern;
		const TCHAR* Name;
		float Fraction;
		const TCHAR* Param;
	};

	const FFallbackEvent GFallbackEvents[] = {
		{ TEXT("melee_*"), TEXT("blade_extend"), 0.08f, TEXT("") },
		{ TEXT("melee_*"), TEXT("melee_hit_begin"), 0.28f, TEXT("") },
		{ TEXT("melee_*"), TEXT("melee_hit_end"), 0.50f, TEXT("") },
		{ TEXT("melee_*"), TEXT("melee_recover"), 0.56f, TEXT("") },
		{ TEXT("melee_*"), TEXT("cancel_window_begin"), 0.56f, TEXT("") },
		{ TEXT("melee_*"), TEXT("blade_retract"), 0.85f, TEXT("") },
		{ TEXT("melee_*"), TEXT("control_return"), 0.80f, TEXT("") },
		{ TEXT("ranged_fire"), TEXT("muzzle_fire"), 0.15f, TEXT("index=0") },
		{ TEXT("ranged_burst"), TEXT("muzzle_fire"), 0.12f, TEXT("index=0") },
		{ TEXT("ranged_burst"), TEXT("muzzle_fire"), 0.42f, TEXT("index=1") },
		{ TEXT("ranged_burst"), TEXT("muzzle_fire"), 0.72f, TEXT("index=2") },
		{ TEXT("reload"), TEXT("reload_eject"), 0.20f, TEXT("") },
		{ TEXT("reload"), TEXT("reload_handoff"), 0.45f, TEXT("") },
		{ TEXT("reload"), TEXT("reload_insert"), 0.70f, TEXT("") },
		{ TEXT("reload"), TEXT("reload_complete"), 0.92f, TEXT("") },
		{ TEXT("reload"), TEXT("control_return"), 0.92f, TEXT("") },
		{ TEXT("cast_directional"), TEXT("cast_release"), 0.45f, TEXT("") },
		{ TEXT("cast_ground"), TEXT("cast_release"), 0.55f, TEXT("") },
		{ TEXT("cast_ground"), TEXT("cancel_window_begin"), 0.80f, TEXT("") },
		{ TEXT("cast_self"), TEXT("cast_release"), 0.50f, TEXT("") },
		{ TEXT("cast_self"), TEXT("cancel_window_begin"), 0.80f, TEXT("") },
		{ TEXT("channel_start"), TEXT("channel_sustain_begin"), 1.00f, TEXT("") },
		{ TEXT("channel_end"), TEXT("channel_release"), 0.25f, TEXT("") },
		{ TEXT("channel_interrupt"), TEXT("channel_interrupted"), 0.00f, TEXT("") },
		{ TEXT("charge_start"), TEXT("charge_full"), 0.90f, TEXT("") },
		{ TEXT("charge_release"), TEXT("charge_release"), 0.30f, TEXT("") },
		{ TEXT("charge_cancel"), TEXT("charge_cancel"), 0.00f, TEXT("") },
		{ TEXT("deploy"), TEXT("deploy_attach"), 0.22f, TEXT("") },
		{ TEXT("deploy"), TEXT("deploy_release"), 0.58f, TEXT("") },
		{ TEXT("deploy"), TEXT("deploy_settle"), 0.90f, TEXT("") },
		{ TEXT("deploy"), TEXT("cancel_window_begin"), 0.90f, TEXT("") },
		{ TEXT("uplink_start"), TEXT("uplink_sustain_begin"), 1.00f, TEXT("") },
		{ TEXT("uplink_end"), TEXT("uplink_complete"), 0.30f, TEXT("") },
		{ TEXT("uplink_cancel"), TEXT("uplink_cancelled"), 0.00f, TEXT("") },
		{ TEXT("dash_*"), TEXT("dash_begin"), 0.00f, TEXT("") },
		{ TEXT("dash_*"), TEXT("dash_end"), 1.00f, TEXT("") },
		{ TEXT("blink_out"), TEXT("blink_vanish"), 0.72f, TEXT("") },
		{ TEXT("blink_in"), TEXT("blink_appear"), 0.00f, TEXT("") },
		{ TEXT("jump_start"), TEXT("jump_takeoff"), 0.55f, TEXT("") },
		{ TEXT("jump_land"), TEXT("land_contact"), 0.00f, TEXT("") },
		{ TEXT("jump_land"), TEXT("control_return"), 0.55f, TEXT("") },
		{ TEXT("land_heavy"), TEXT("land_contact"), 0.00f, TEXT("") },
		{ TEXT("land_heavy"), TEXT("land_impact_heavy"), 0.10f, TEXT("") },
		{ TEXT("land_heavy"), TEXT("control_return"), 0.72f, TEXT("") },
		{ TEXT("hit_*"), TEXT("hit_peak"), 0.30f, TEXT("") },
		{ TEXT("stun_start"), TEXT("stun_begin"), 0.00f, TEXT("") },
		{ TEXT("knockup_start"), TEXT("knockup_launch"), 0.40f, TEXT("") },
		{ TEXT("knockdown_*"), TEXT("ground_impact"), 0.60f, TEXT("") },
		{ TEXT("getup_*"), TEXT("getup_stand"), 0.90f, TEXT("") },
		{ TEXT("sleep_start"), TEXT("sleep_settle"), 0.85f, TEXT("") },
		{ TEXT("death_*"), TEXT("death_impact"), 0.55f, TEXT("") },
		{ TEXT("respawn"), TEXT("respawn_activate"), 0.50f, TEXT("") },
		{ TEXT("respawn"), TEXT("control_return"), 0.90f, TEXT("") },
		{ TEXT("greet"), TEXT("control_return"), 0.80f, TEXT("") },
		{ TEXT("victory"), TEXT("control_return"), 0.85f, TEXT("") },
		{ TEXT("defeat"), TEXT("control_return"), 0.85f, TEXT("") },
		{ TEXT("dialogue"), TEXT("dialogue_start"), 0.00f, TEXT("") },
		{ TEXT("dialogue"), TEXT("dialogue_end"), 1.00f, TEXT("") },
	};

	TMap<FName, FString> ParseParams(const TCHAR* S)
	{
		TMap<FName, FString> M;
		FString Str(S);
		if (Str.IsEmpty()) return M;
		FString K, V;
		if (Str.Split(TEXT("="), &K, &V)) M.Add(FName(*K), V);
		return M;
	}

	int32 ActionPriorityOf(EOperativeAction A)
	{
		switch (A)
		{
		case EOperativeAction::Melee: case EOperativeAction::Reload: case EOperativeAction::CastGround:
		case EOperativeAction::CastSelf: case EOperativeAction::Deploy: return 40;
		case EOperativeAction::Channel: case EOperativeAction::Charge: case EOperativeAction::Uplink: return 45;
		default: return 20;
		}
	}

	inline float Smooth01(float X) { X = FMath::Clamp(X, 0.f, 1.f); return X * X * (3.f - 2.f * X); }
}

// ------------------------------------------------------------------------------------------------ basics

UOperativeActionComponent::UOperativeActionComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UOperativeActionComponent::BeginPlay()
{
	Super::BeginPlay();
	Library = UOperativeLibrary::Get(this);
	Recipe.bSecondary = true;
}

AOperativeCharacter* UOperativeActionComponent::Host() const
{
	return Cast<AOperativeCharacter>(GetOwner());
}

bool UOperativeActionComponent::IsGrounded() const
{
	const AOperativeCharacter* H = Host();
	return H && H->IsGroundedForActions();
}

float UOperativeActionComponent::RelativeAngleLeft(const FVector& WorldDir) const
{
	const AOperativeCharacter* H = Host();
	if (!H) return 0.f;
	const FVector D = WorldDir.GetSafeNormal2D();
	if (D.IsNearlyZero()) return 0.f;
	const float DirYaw = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X));
	return -FMath::FindDeltaAngleDegrees(H->GetActorRotation().Yaw, DirYaw);
}

const TArray<FOperativeEventDef>& UOperativeActionComponent::EventsFor(FName ClipId)
{
	if (const TUniquePtr<TArray<FOperativeEventDef>>* Found = EventCache.Find(ClipId)) return **Found;
	TArray<FOperativeEventDef> List;
	float Length = 0.f;
	if (const UOperativeLibrary* L = Lib())
	{
		if (const FOperativeClipInfo* Info = L->FindClip(ClipId))
		{
			List = Info->Events;
			Length = Info->Length();
		}
	}
	const FString Id = ClipId.ToString();
	for (const FFallbackEvent& F : GFallbackEvents)
	{
		if (!Id.MatchesWildcard(F.ClipPattern)) continue;
		const FName EvName(F.Name);
		// the manifest wins: a clip that has an event of this name gets no synthetic copy and its authored time is never moved
		bool bHas = false;
		for (const FOperativeEventDef& E : List)
		{
			if (E.Name == EvName && !E.bSynthetic) { bHas = true; break; }
		}
		if (bHas) continue;
		FOperativeEventDef E;
		E.Name = EvName;
		E.TimeS = F.Fraction * Length;
		E.Frame = FMath::RoundToInt(E.TimeS * 30.f);
		E.Params = ParseParams(F.Param);
		E.bSynthetic = true;
		List.Add(E);
	}
	List.StableSort([](const FOperativeEventDef& A, const FOperativeEventDef& B) { return A.TimeS < B.TimeS; });
	TUniquePtr<TArray<FOperativeEventDef>>& Slot = EventCache.Add(ClipId, MakeUnique<TArray<FOperativeEventDef>>(MoveTemp(List)));
	return *Slot;
}

bool UOperativeActionComponent::StartPlayer(FOperativePlayer& P, FName ClipId, float Rate, bool bLoop, float StartTime, FName Role)
{
	P.Reset();
	P.Role = Role;
	UOperativeLibrary* L = Lib();
	const FOperativeClipInfo* Info = L ? L->FindClip(ClipId) : nullptr;
	if (!Info || !Info->Sequence)
	{
		UE_LOG(LogMorphRig, Warning, TEXT("Action: clip %s is not available"), *ClipId.ToString());
		return false;
	}
	P.ClipId = ClipId;
	P.Info = Info;
	P.Length = FMath::Max(Info->Length(), 1.f / 60.f);
	P.Rate = Rate;
	P.bLoop = bLoop;
	P.Time = FMath::Clamp(StartTime, 0.f, P.Length);
	P.bActive = true;
	P.PassId = NextPassId++;
	P.Events = &EventsFor(ClipId);
	P.NextEvent = 0;
	if (StartTime > 0.f)
	{
		while (P.NextEvent < P.Events->Num() && (*P.Events)[P.NextEvent].TimeS < StartTime - 1e-4f) ++P.NextEvent;
	}
	return true;
}

void UOperativeActionComponent::EmitEvent(FName Name, FName ClipId, float ClipTime, FName Role, const FString& Params, bool bSynthetic, int32 PassId)
{
	FOperativeEventInfo Info;
	Info.Name = Name;
	Info.ClipId = ClipId;
	Info.ClipTime = ClipTime;
	Info.WorldTime = LocalTime;
	Info.Params = Params;
	Info.bSynthetic = bSynthetic;
	Info.PassId = PassId;
	Info.Player = Role;
	++TotalEvents;
	RecentEvents.Add(Info);
	if (RecentEvents.Num() > 24) RecentEvents.RemoveAt(0, RecentEvents.Num() - 24, EAllowShrinking::No);
	HandleEvent(Info);
	OnEvent.Broadcast(Info);
}

void UOperativeActionComponent::FireEventAt(const FOperativePlayer& P, int32 Index, float Time)
{
	const FOperativeEventDef& Ev = (*P.Events)[Index];
	// once per pass guard: key = pass id, role and event index
	const uint64 RoleBits = P.Role == FName("upper") ? 1 : (P.Role == FName("base") ? 0 : 2);
	const uint64 Key = ((uint64)(uint32)P.PassId << 32) | (uint64)(uint32)(Index & 0xFFFF) | (RoleBits << 16);
	if (FiredKeys.Contains(Key))
	{
		++DuplicateEventCount;
		UE_LOG(LogMorphRig, Warning, TEXT("Action: duplicate event %s in pass %d of %s"), *Ev.Name.ToString(), P.PassId, *P.ClipId.ToString());
		return;
	}
	FiredKeys.Add(Key);
	if (FiredKeys.Num() > 4096) FiredKeys.Reset();
	EmitEvent(Ev.Name, P.ClipId, Time, P.Role, Ev.ParamString(), Ev.bSynthetic, P.PassId);
}

void UOperativeActionComponent::AdvancePlayer(FOperativePlayer& P, float Dt)
{
	if (!P.bActive || !P.Events || P.bPaused) return;
	// fires events up to T; returns false when a handler restarted or reset the player
	auto FireUpTo = [&](float T) -> bool
	{
		while (P.Events && P.NextEvent < P.Events->Num() && (*P.Events)[P.NextEvent].TimeS <= T + 1e-4f)
		{
			const int32 Pass = P.PassId;
			const int32 Idx = P.NextEvent;
			P.NextEvent = Idx + 1;   // advance first: the event can never fire twice in one pass
			FireEventAt(P, Idx, FMath::Min(T, P.Length));
			if (!P.bActive || P.PassId != Pass) return false;
		}
		return true;
	};
	const int32 Pass0 = P.PassId;
	const float NewTime = P.Time + Dt * P.Rate;
	if (P.bLoop)
	{
		if (NewTime >= P.Length)
		{
			P.Time = P.Length;
			if (!FireUpTo(P.Length) || P.PassId != Pass0) return;
			P.PassId = NextPassId++;
			P.NextEvent = 0;
			P.Time = FMath::Fmod(NewTime, P.Length);
			FireUpTo(P.Time);
		}
		else
		{
			P.Time = NewTime;
			FireUpTo(P.Time);
		}
	}
	else
	{
		P.Time = FMath::Min(NewTime, P.Length);
		if (!FireUpTo(P.Time)) return;
		if (NewTime >= P.Length) P.bFinished = true;
	}
}

// ------------------------------------------------------------------------------------------------ snapshot and base

void UOperativeActionComponent::RequestSnapshot(float BlendTime)
{
	if (BlendTime <= 0.f) return;
	++SnapshotSerial;
	SnapshotDuration = FMath::Max(BlendTime, 0.02f);
	SnapshotElapsed = 0.f;
}

void UOperativeActionComponent::PlayBase(FName ClipId, float Rate, bool bLoop, float BlendTime, float StartTime)
{
	RequestSnapshot(BlendTime);
	StartPlayer(Base, ClipId, Rate, bLoop, StartTime, FName("base"));
}

FName UOperativeActionComponent::StanceIdleClip() const
{
	switch (GetStance())
	{
	case EOperativeStance::Wounded: return FName("idle_wounded");
	case EOperativeStance::Combat: return FName("idle_combat");
	default: return FName("idle_relaxed");
	}
}

EOperativeStance UOperativeActionComponent::GetStance() const
{
	if (bWoundedOverride || Health < 0.35f) return EOperativeStance::Wounded;
	if (bCombatStance || AimActive || AimHoldTimer > 0.f) return EOperativeStance::Combat;
	return EOperativeStance::Relaxed;
}

int32 UOperativeActionComponent::GetCurrentPriority() const
{
	switch (State)
	{
	case EOperativeState::Locomotion: return LocoSub == ELocoSub::Idle ? 0 : 10;
	case EOperativeState::Airborne: return 30;
	case EOperativeState::Dash: case EOperativeState::Blink: return 55;
	case EOperativeState::Action: return ActionPriorityOf(Action);
	case EOperativeState::Stun: return 70;
	case EOperativeState::Sleep: return 75;
	case EOperativeState::Knockback: return 65;
	case EOperativeState::Knockup: case EOperativeState::Knockdown: return 85;
	case EOperativeState::Respawning: return 95;
	case EOperativeState::Dying: case EOperativeState::Dead: return 100;
	case EOperativeState::Viewer: return 50;
	}
	return 0;
}

bool UOperativeActionComponent::HasControl() const
{
	switch (State)
	{
	case EOperativeState::Locomotion: return LocoSub != ELocoSub::Turn && LocoSub != ELocoSub::Pivot;
	case EOperativeState::Airborne: return true;
	case EOperativeState::Action: return bControlReturned;
	default: return false;
	}
}

FString UOperativeActionComponent::GetStateString() const
{
	static const TCHAR* StateNames[] = { TEXT("Locomotion"), TEXT("Airborne"), TEXT("Dash"), TEXT("Blink"), TEXT("Action"), TEXT("Stun"), TEXT("Sleep"), TEXT("Knockback"), TEXT("Knockup"), TEXT("Knockdown"), TEXT("Dying"), TEXT("Dead"), TEXT("Respawning"), TEXT("Viewer") };
	FString S = StateNames[(int32)State];
	switch (State)
	{
	case EOperativeState::Locomotion:
	{
		static const TCHAR* Sub[] = { TEXT("Idle"), TEXT("Start"), TEXT("Move"), TEXT("Stop"), TEXT("Turn"), TEXT("Pivot") };
		S += FString(TEXT("/")) + Sub[(int32)LocoSub];
		break;
	}
	case EOperativeState::Airborne:
	{
		static const TCHAR* Sub[] = { TEXT("JumpStart"), TEXT("JumpAir"), TEXT("Fall"), TEXT("Land"), TEXT("LandHeavy") };
		S += FString(TEXT("/")) + Sub[(int32)AirSub];
		break;
	}
	case EOperativeState::Action:
	{
		static const TCHAR* Sub[] = { TEXT("None"), TEXT("Melee"), TEXT("Reload"), TEXT("CastGround"), TEXT("CastSelf"), TEXT("Channel"), TEXT("Charge"), TEXT("Deploy"), TEXT("Uplink"), TEXT("Greet"), TEXT("Victory"), TEXT("Defeat"), TEXT("Dialogue") };
		S += FString(TEXT("/")) + Sub[(int32)Action] + FString::Printf(TEXT("#%d"), Phase);
		break;
	}
	default:
		break;
	}
	if (Upper.bActive) S += FString(TEXT(" +upper:")) + Upper.ClipId.ToString();
	if (AimActive) S += TEXT(" +aim");
	return S;
}

void UOperativeActionComponent::SetState(EOperativeState NewState)
{
	State = NewState;
	bCancelWindow = false;
	bControlReturned = false;
	bReleaseRequested = bCancelRequested = bInterruptRequested = false;
	bComboQueued = false;
	Phase = 0;
	ActionTimer = 0.f;
}

void UOperativeActionComponent::ClearUpper(float Fade)
{
	UpperTargetAlpha = 0.f;
	if (Fade <= 0.f)
	{
		UpperAlpha = 0.f;
		Upper.Reset();
	}
	bUpperQueued = false;
}

void UOperativeActionComponent::SetSilence(bool b)
{
	bSilenced = b;
	if (b) InterruptAction(EOperativeInterrupt::Silence);
}

void UOperativeActionComponent::SetDisarm(bool b)
{
	bDisarmed = b;
	if (b && Upper.bActive && (UpperKind == EOperativeUpper::RangedFire || UpperKind == EOperativeUpper::RangedBurst)) ClearUpper(0.f);
}

void UOperativeActionComponent::SetFootIK(bool bEnabled, float PelvisOffset, const FOperativeFootIK& Left, const FOperativeFootIK& Right)
{
	bFootIKInput = bEnabled;
	PelvisOffsetInput = PelvisOffset;
	FootInput[0] = Left;
	FootInput[1] = Right;
}

// ------------------------------------------------------------------------------------------------ event handling (state machine side)

void UOperativeActionComponent::HandleEvent(const FOperativeEventInfo& Info)
{
	AOperativeCharacter* H = Host();
	const FName N = Info.Name;
	const bool bViewer = (State == EOperativeState::Viewer);
	if (N == FName("control_return")) { bControlReturned = true; return; }
	if (N == FName("cancel_window_begin")) { bCancelWindow = true; return; }
	if (N == FName("cancel_window_end")) { bCancelWindow = false; return; }
	if (N == FName("melee_hit_begin")) { bMeleeWindow = true; ++MeleeWindowSerial; return; }
	if (N == FName("melee_hit_end")) { bMeleeWindow = false; return; }
	if (N == FName("melee_recover")) { bCancelWindow = true; bMeleeWindow = false; return; }
	if (bViewer) return;   // viewer playback only displays events; no gameplay side effects
	if (!H) return;
	if (N == FName("jump_takeoff")) { if (!bJumpTookOff) { H->HostJump(); bJumpTookOff = true; } return; }
	if (N == FName("blink_appear")) { H->HostSetMeshVisible(true); return; }
	if (N == FName("blink_vanish")) { if (!bBlinkTeleported) { H->HostBlinkTeleport(BlinkDir, BlinkDist); bBlinkTeleported = true; } return; }
	if (N == FName("knockup_launch"))
	{
		if (!bKnockLaunched)
		{
			bKnockLaunched = true;
			FVector V = KnockTravelDir.GetSafeNormal2D() * FMath::Max(KnockDistance, 0.f);
			V.Z = KnockLaunchSpeed;
			H->HostLaunch(V);
		}
		return;
	}
	if (N == FName("channel_sustain_begin")) { bChannelSustain = true; return; }
	if (N == FName("charge_full")) { bChargeFullFired = true; ChargeTime = FMath::Max(ChargeTime, ChargeFullTime); return; }
	if (N == FName("channel_release") || N == FName("channel_interrupted")) { bChannelSustain = false; return; }
	if (N == FName("deploy_attach")) { H->HostRecallBeacon(); return; }
	if (N == FName("deploy_release")) { H->HostSpawnBeacon(); return; }
	if (N == FName("respawn_activate")) { H->HostOnRespawn(); return; }
}

// ------------------------------------------------------------------------------------------------ commands

bool UOperativeActionComponent::CanStartAction(int32 NewPriority, bool bSustainedCancel) const
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) return true;
	switch (State)
	{
	case EOperativeState::Locomotion: return true;
	case EOperativeState::Airborne: return false;
	case EOperativeState::Action:
	{
		const int32 Cur = ActionPriorityOf(Action);
		if (bSustainedCancel && Cur >= 45) return true;
		return (bControlReturned || bCancelWindow) && NewPriority >= Cur - 5;
	}
	default: return false;
	}
}

bool UOperativeActionComponent::CanStartUpper() const
{
	if (State != EOperativeState::Locomotion) return false;
	return LocoSub != ELocoSub::Turn && LocoSub != ELocoSub::Pivot;
}

bool UOperativeActionComponent::RequestJump()
{
	if (!IsAlive() || bRooted || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	const bool bFromAction = State == EOperativeState::Action && bControlReturned && ActionPriorityOf(Action) <= 40;
	if ((State != EOperativeState::Locomotion && !bFromAction) || !IsGrounded()) return false;
	if (bFromAction) FinishAction(0.f);
	ClearUpper(0.f);
	SetState(EOperativeState::Airborne);
	AirSub = EAirSub::JumpStart;
	AirTime = 0.f;
	MinZVel = 0.f;
	bJumpTookOff = false;
	PlayBase(FName("jump_start"), ActionRate, false, 0.12f);
	return true;
}

bool UOperativeActionComponent::RequestDash(const FVector& WorldDir)
{
	if (!IsAlive() || bRooted || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	bool bOk = State == EOperativeState::Locomotion && IsGrounded();
	if (State == EOperativeState::Action)
	{
		const bool bSustained = (Action == EOperativeAction::Channel || Action == EOperativeAction::Charge || Action == EOperativeAction::Uplink);
		bOk = IsGrounded() && (bSustained || bCancelWindow || bControlReturned);
	}
	if (!bOk) return false;
	if (State == EOperativeState::Action) CancelActionState(false);
	AOperativeCharacter* H = Host();
	FVector Dir = WorldDir.GetSafeNormal2D();
	if (Dir.IsNearlyZero()) Dir = H->GetActorForwardVector();
	const float Theta = RelativeAngleLeft(Dir);
	FName Clip = FName("dash_f");
	if (FMath::Abs(Theta) <= 45.f) Clip = FName("dash_f");
	else if (FMath::Abs(Theta) >= 135.f) Clip = FName("dash_b");
	else Clip = Theta > 0.f ? FName("dash_l") : FName("dash_r");
	ClearUpper(0.f);
	SetState(EOperativeState::Dash);
	DashYaw = H->GetActorRotation().Yaw;
	PlayBase(Clip, ActionRate, false, 0.06f);
	DashPrevTime = 0.f;
	return true;
}

bool UOperativeActionComponent::RequestBlink(const FVector& WorldDir, float Distance)
{
	if (!IsAlive() || bRooted || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	bool bOk = State == EOperativeState::Locomotion && IsGrounded();
	if (State == EOperativeState::Action)
	{
		const bool bSustained = (Action == EOperativeAction::Channel || Action == EOperativeAction::Charge || Action == EOperativeAction::Uplink);
		bOk = IsGrounded() && (bSustained || bCancelWindow || bControlReturned);
	}
	if (!bOk) return false;
	if (State == EOperativeState::Action) CancelActionState(false);
	AOperativeCharacter* H = Host();
	BlinkDir = WorldDir.GetSafeNormal2D();
	if (BlinkDir.IsNearlyZero()) BlinkDir = H->GetActorForwardVector();
	BlinkDist = Distance;
	bBlinkTeleported = false;
	ClearUpper(0.f);
	SetState(EOperativeState::Blink);
	Phase = 0;
	PlayBase(FName("blink_out"), ActionRate, false, 0.08f);
	return true;
}

void UOperativeActionComponent::EnterAction(EOperativeAction Which, FName FirstClip, float Rate, bool bLoop, float BlendTime)
{
	ClearUpper(0.f);
	SetState(EOperativeState::Action);
	Action = Which;
	Phase = 0;
	bControlReturned = false;
	bCancelWindow = false;
	bChannelSustain = false;
	ChargeActive = false;
	ChargeTime = 0.f;
	bChargeFullFired = false;
	if (Which == EOperativeAction::Charge)
	{
		// the charge is full when the charge_full marker of charge_start is reached (manifest time, or the fallback fraction)
		ChargeFullTime = 1.4f;
		for (const FOperativeEventDef& E : EventsFor(FirstClip))
		{
			if (E.Name == FName("charge_full")) { ChargeFullTime = FMath::Max(E.TimeS, 0.1f); break; }
		}
	}
	PlayBase(FirstClip, Rate, bLoop, BlendTime);
}

bool UOperativeActionComponent::RequestMelee()
{
	if (!IsAlive() || bDisarmed || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (State == EOperativeState::Action && Action == EOperativeAction::Melee)
	{
		// combo: queued now, consumed when the recover / cancel window opens (or right away if it already is open)
		bComboQueued = true;
		return true;
	}
	if (!CanStartAction(40, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	ComboIndex = 1;
	EnterAction(EOperativeAction::Melee, FName("melee_1"), ActionRate, false, 0.10f);
	bMeleeWindow = false;
	return true;
}

bool UOperativeActionComponent::RequestReload()
{
	if (!IsAlive() || bDisarmed || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(40, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::Reload, FName("reload"), ActionRate, false, 0.15f);
	return true;
}

bool UOperativeActionComponent::RequestCastGround()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(40, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::CastGround, FName("cast_ground"), ActionRate, false, 0.15f);
	return true;
}

bool UOperativeActionComponent::RequestCastSelf()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(40, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::CastSelf, FName("cast_self"), ActionRate, false, 0.15f);
	return true;
}

bool UOperativeActionComponent::RequestChannelStart()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(45, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::Channel, FName("channel_start"), ActionRate, false, 0.15f);
	return true;
}

void UOperativeActionComponent::RequestChannelRelease()
{
	if (State == EOperativeState::Action && Action == EOperativeAction::Channel) bReleaseRequested = true;
}

bool UOperativeActionComponent::RequestChargeStart()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(45, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::Charge, FName("charge_start"), ActionRate, false, 0.15f);
	ChargeActive = true;
	return true;
}

void UOperativeActionComponent::RequestChargeRelease()
{
	if (State == EOperativeState::Action && Action == EOperativeAction::Charge && Phase <= 1) bReleaseRequested = true;
}

void UOperativeActionComponent::RequestChargeCancel()
{
	if (State == EOperativeState::Action && Action == EOperativeAction::Charge && Phase <= 1) bCancelRequested = true;
}

bool UOperativeActionComponent::RequestDeploy()
{
	if (!IsAlive() || bDisarmed || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(40, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::Deploy, FName("deploy"), ActionRate, false, 0.15f);
	return true;
}

bool UOperativeActionComponent::RequestUplinkStart()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartAction(45, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	EnterAction(EOperativeAction::Uplink, FName("uplink_start"), ActionRate, false, 0.15f);
	return true;
}

void UOperativeActionComponent::RequestUplinkCancel()
{
	if (State == EOperativeState::Action && Action == EOperativeAction::Uplink && Phase <= 1) bCancelRequested = true;
}

bool UOperativeActionComponent::RequestEmote(EOperativeAction Which)
{
	if (!IsAlive() || bStasis) return false;
	if (Which != EOperativeAction::Greet && Which != EOperativeAction::Victory && Which != EOperativeAction::Defeat) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	const bool bIdleish = State == EOperativeState::Locomotion && (LocoSub == ELocoSub::Idle || LocoSub == ELocoSub::Stop);
	if (!bIdleish && !CanStartAction(20, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	const FName Clip = Which == EOperativeAction::Greet ? FName("greet") : Which == EOperativeAction::Victory ? FName("victory") : FName("defeat");
	EnterAction(Which, Clip, ActionRate, false, 0.2f);
	return true;
}

bool UOperativeActionComponent::RequestDialogue()
{
	if (!IsAlive() || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	const bool bIdleish = State == EOperativeState::Locomotion && (LocoSub == ELocoSub::Idle || LocoSub == ELocoSub::Stop);
	if (!bIdleish && !CanStartAction(20, false)) return false;
	if (State == EOperativeState::Action) FinishAction(0.f);
	// dialogue always plays at rate 1 so the audio stays in sync
	EnterAction(EOperativeAction::Dialogue, FName("dialogue"), 1.f, false, 0.25f);
	if (UOperativeFaceComponent* F = Host() ? Host()->Face.Get() : nullptr) { F->SetAutoBlink(false); F->SetClipFaceWeight(1.f); }
	// the wav starts together with clip frame 0 (manifest: procedural_components.audio_offset_s = 0, lead-in silence is inside the wav)
	if (AOperativeCharacter* H = Host()) { H->HostPlayDialogue(); bDialogueAudio = true; }
	return true;
}

void UOperativeActionComponent::StopDialogue()
{
	if (State == EOperativeState::Action && Action == EOperativeAction::Dialogue) FinishAction(0.25f);
}

namespace
{
	FName UpperClipFor(EOperativeUpper K)
	{
		switch (K)
		{
		case EOperativeUpper::RangedFire: return FName("ranged_fire");
		case EOperativeUpper::RangedBurst: return FName("ranged_burst");
		default: return FName("cast_directional");
		}
	}
}

bool UOperativeActionComponent::RequestFire()
{
	if (!IsAlive() || bDisarmed || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartUpper()) return false;
	AimHoldTimer = 2.0f;
	if (Upper.bActive && !Upper.bFinished)
	{
		if (UpperKind == EOperativeUpper::RangedFire && Upper.Time >= 0.55f * Upper.Length) { /* re-trigger below */ }
		else { bUpperQueued = true; UpperQueuedKind = EOperativeUpper::RangedFire; return true; }
	}
	UpperKind = EOperativeUpper::RangedFire;
	StartPlayer(Upper, UpperClipFor(UpperKind), ActionRate, false, 0.f, FName("upper"));
	UpperTargetAlpha = 1.f;
	return Upper.bActive;
}

bool UOperativeActionComponent::RequestBurst()
{
	if (!IsAlive() || bDisarmed || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartUpper()) return false;
	AimHoldTimer = 2.0f;
	if (Upper.bActive && !Upper.bFinished)
	{
		if (UpperKind == EOperativeUpper::RangedBurst && Upper.Time >= 0.7f * Upper.Length) { /* re-trigger below */ }
		else { bUpperQueued = true; UpperQueuedKind = EOperativeUpper::RangedBurst; return true; }
	}
	UpperKind = EOperativeUpper::RangedBurst;
	StartPlayer(Upper, UpperClipFor(UpperKind), ActionRate, false, 0.f, FName("upper"));
	UpperTargetAlpha = 1.f;
	return Upper.bActive;
}

bool UOperativeActionComponent::RequestCastDirectional()
{
	if (!IsAlive() || bSilenced || bStasis) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (!CanStartUpper()) return false;
	AimHoldTimer = 2.0f;
	if (Upper.bActive && !Upper.bFinished)
	{
		if (UpperKind == EOperativeUpper::CastDirectional && Upper.Time >= 0.7f * Upper.Length) { /* re-trigger below */ }
		else { bUpperQueued = true; UpperQueuedKind = EOperativeUpper::CastDirectional; return true; }
	}
	UpperKind = EOperativeUpper::CastDirectional;
	StartPlayer(Upper, UpperClipFor(UpperKind), ActionRate, false, 0.f, FName("upper"));
	UpperTargetAlpha = 1.f;
	return Upper.bActive;
}

void UOperativeActionComponent::InterruptAction(EOperativeInterrupt Reason)
{
	if (State != EOperativeState::Action) return;
	if (Action == EOperativeAction::Channel || Action == EOperativeAction::Uplink || Action == EOperativeAction::Charge)
	{
		bInterruptRequested = true;
		InterruptReason = Reason;
		return;
	}
	if (Action == EOperativeAction::Dialogue || Action == EOperativeAction::Greet || Action == EOperativeAction::Victory || Action == EOperativeAction::Defeat)
	{
		FinishAction(0.2f);
	}
}

void UOperativeActionComponent::CancelActionState(bool bSilent)
{
	// hard cancel used when another action, a disable or death takes over: cleans flags and effects
	if (bChannelSustain && !bSilent)
	{
		EmitEvent(FName("channel_interrupted"), Base.ClipId, Base.Time, FName("gameplay"), TEXT("reason=cancel"), false, 0);
	}
	bChannelSustain = false;
	ChargeActive = false;
	ChargeTime = 0.f;
	bMeleeWindow = false;
	if (Host() && bDialogueAudio) { Host()->HostStopDialogue(); bDialogueAudio = false; }
	if (Action == EOperativeAction::Dialogue)
	{
		if (UOperativeFaceComponent* F = Host() ? Host()->Face.Get() : nullptr) { F->SetAutoBlink(true); }
	}
	Action = EOperativeAction::None;
}

void UOperativeActionComponent::FinishAction(float BlendTime)
{
	CancelActionState(true);
	EnterLocomotion(BlendTime);
}

void UOperativeActionComponent::ApplyHit(const FVector& HitTravelDir, float Damage)
{
	if (!IsAlive()) return;
	if (Damage > 0.f) Health = FMath::Clamp(Health - Damage, 0.f, 1.f);
	if (State == EOperativeState::Sleep) WakeUp();
	if (State == EOperativeState::Action && (Action == EOperativeAction::Channel || Action == EOperativeAction::Uplink || Action == EOperativeAction::Charge) && Damage > 0.f)
	{
		InterruptAction(EOperativeInterrupt::Damage);
	}
	AimHoldTimer = FMath::Max(AimHoldTimer, 1.0f);
	// the hit arrives from the opposite of its travel direction
	const float Theta = RelativeAngleLeft(-HitTravelDir);
	FName Clip;
	if (FMath::Abs(Theta) <= 45.f) Clip = FName("hit_f");
	else if (FMath::Abs(Theta) >= 135.f) Clip = FName("hit_b");
	else Clip = Theta > 0.f ? FName("hit_l") : FName("hit_r");
	// slot choice: a finished slot, otherwise the older one
	int32 Slot = 0;
	if (HitPlayer[0].bActive && !HitPlayer[0].bFinished)
	{
		Slot = (HitPlayer[1].bActive && !HitPlayer[1].bFinished) ? (HitPlayer[0].Time >= HitPlayer[1].Time ? 0 : 1) : 1;
	}
	StartPlayer(HitPlayer[Slot], Clip, 1.f, false, 0.f, FName(Slot == 0 ? "hit0" : "hit1"));
	if (Damage > 0.f && Health <= 0.f) Kill(HitTravelDir);
}

void UOperativeActionComponent::StartDisable(EDisableKind Kind, FName FirstClip, float Duration)
{
	AOperativeCharacter* H = Host();
	// death overrides, disables override actions (see priorities)
	if (Action != EOperativeAction::None || State == EOperativeState::Action)
	{
		if (Action == EOperativeAction::Channel || Action == EOperativeAction::Uplink || Action == EOperativeAction::Charge)
		{
			// no interrupt clip: the disable takes over from the current pose (snapshot blend)
		}
		CancelActionState(false);
	}
	ClearUpper(0.f);
	if (H) H->HostSetMeshVisible(true);
	EOperativeState NewState = EOperativeState::Stun;
	switch (Kind)
	{
	case EDisableKind::Stun: NewState = EOperativeState::Stun; break;
	case EDisableKind::Sleep: NewState = EOperativeState::Sleep; break;
	case EDisableKind::Knockback: NewState = EOperativeState::Knockback; break;
	case EDisableKind::Knockup: NewState = EOperativeState::Knockup; break;
	case EDisableKind::Knockdown: NewState = EOperativeState::Knockdown; break;
	default: break;
	}
	SetState(NewState);
	Disable = Kind;
	DisableTimer = Duration;
	bKnockLaunched = false;
	PlayBase(FirstClip, ActionRate, false, 0.12f);
}

bool UOperativeActionComponent::ApplyStun(float Duration)
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (State == EOperativeState::Stun) { DisableTimer = FMath::Max(DisableTimer, Duration); return true; }
	if (GetCurrentPriority() >= 70) return false;
	StartDisable(EDisableKind::Stun, FName("stun_start"), Duration);
	return true;
}

bool UOperativeActionComponent::ApplySleep(float Duration)
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (State == EOperativeState::Sleep) { DisableTimer = FMath::Max(DisableTimer, Duration); return true; }
	if (GetCurrentPriority() >= 75) return false;
	StartDisable(EDisableKind::Sleep, FName("sleep_start"), Duration);
	return true;
}

bool UOperativeActionComponent::ApplyKnockback(const FVector& TravelDir, float Distance)
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (GetCurrentPriority() >= 65) return false;
	KnockTravelDir = TravelDir.GetSafeNormal2D();
	KnockDistance = Distance;
	StartDisable(EDisableKind::Knockback, FName("knockback"), 0.f);
	return true;
}

bool UOperativeActionComponent::ApplyKnockup(const FVector& TravelDir, float LaunchSpeed)
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (GetCurrentPriority() >= 85) return false;
	KnockTravelDir = TravelDir.GetSafeNormal2D();
	KnockDistance = 60.f;
	KnockLaunchSpeed = LaunchSpeed;
	StartDisable(EDisableKind::Knockup, FName("knockup_start"), 0.f);
	return true;
}

void UOperativeActionComponent::ToKnockdown(const FVector& HitTravelDir, float BlendTime)
{
	// hit from the front pushes the character backwards: it lands on its back (knockdown_back / face up)
	bHitFromFront = FMath::Abs(RelativeAngleLeft(-HitTravelDir)) < 90.f;
	bFaceDown = !bHitFromFront;
	if (State != EOperativeState::Knockdown)
	{
		if (State == EOperativeState::Action) CancelActionState(false);
		ClearUpper(0.f);
		SetState(EOperativeState::Knockdown);
	}
	Disable = EDisableKind::Knockdown;
	Phase = 0;
	DisableTimer = 0.9f;
	PlayBase(bFaceDown ? FName("knockdown_front") : FName("knockdown_back"), ActionRate, false, BlendTime);
}

bool UOperativeActionComponent::ApplyKnockdown(const FVector& HitTravelDir)
{
	if (!IsAlive()) return false;
	if (State == EOperativeState::Viewer) StopViewer();
	if (GetCurrentPriority() >= 85) return false;
	KnockTravelDir = HitTravelDir.GetSafeNormal2D();
	if (State == EOperativeState::Action) CancelActionState(false);
	ToKnockdown(HitTravelDir, 0.12f);
	return true;
}

void UOperativeActionComponent::WakeUp()
{
	if (State == EOperativeState::Sleep && Phase < 2)
	{
		Phase = 2;
		PlayBase(FName("sleep_end"), ActionRate, false, 0.15f);
	}
}

void UOperativeActionComponent::Kill(const FVector& HitTravelDir)
{
	if (bDeadOnce || State == EOperativeState::Dying || State == EOperativeState::Dead || State == EOperativeState::Respawning) return;
	KillInternal(HitTravelDir);
}

void UOperativeActionComponent::KillInternal(const FVector& HitTravelDir)
{
	AOperativeCharacter* H = Host();
	bDeadOnce = true;
	Health = 0.f;
	if (State == EOperativeState::Action) CancelActionState(false);
	CancelActionState(true);
	ClearUpper(0.f);
	HitPlayer[0].Reset();
	HitPlayer[1].Reset();
	bMeleeWindow = false;
	bChannelSustain = false;
	if (H) { H->HostSetMeshVisible(true); H->HostOnDeath(); }
	bDeathFront = FMath::Abs(RelativeAngleLeft(-HitTravelDir)) < 90.f;
	SetState(EOperativeState::Dying);
	Disable = EDisableKind::None;
	PlayBase(bDeathFront ? FName("death_front") : FName("death_back"), ActionRate, false, 0.10f);
	DeathHoldTime = 0.f;
}

void UOperativeActionComponent::Respawn()
{
	if (State != EOperativeState::Dead) return;
	SetState(EOperativeState::Respawning);
	bDeadOnce = false;
	Health = 1.f;
	ResetProps();
	if (AOperativeCharacter* H = Host()) H->HostResetProps();
	PlayBase(FName("respawn"), ActionRate, false, 0.15f);
	++Recipe.SecondaryResetSerial;
}

void UOperativeActionComponent::ResetProps()
{
	bMeleeWindow = false;
	bChannelSustain = false;
	ChargeActive = false;
}

void UOperativeActionComponent::ResetAll()
{
	CancelActionState(true);
	ClearUpper(0.f);
	HitPlayer[0].Reset();
	HitPlayer[1].Reset();
	bDeadOnce = false;
	Health = 1.f;
	bRooted = bSilenced = bDisarmed = bStasis = false;
	bCombatStance = false;
	bWoundedOverride = false;
	AimHoldTimer = 0.f;
	bAimHold = false;
	ActionRate = 1.f;
	Disable = EDisableKind::None;
	Action = EOperativeAction::None;
	LocoSub = ELocoSub::Idle;
	State = EOperativeState::Locomotion;
	Phase = 0;
	LocoPhase = 0.f;
	MoveDir = FVector::ZeroVector;
	DesiredSpeed = 0.f;
	bMeleeWindow = false;
	if (AOperativeCharacter* H = Host()) { H->HostResetProps(); H->HostSetMeshVisible(true); }
	if (UOperativeFaceComponent* F = Host() ? Host()->Face.Get() : nullptr) { F->ClearAll(); F->SetAutoBlink(true); }
	++Recipe.SecondaryResetSerial;
	PlayBase(StanceIdleClip(), 1.f, true, 0.15f);
	Out = FHostOutput();
}

// ------------------------------------------------------------------------------------------------ viewer

bool UOperativeActionComponent::PlayClip(FName ClipId, float Rate, bool bForceLoop, float StartTime)
{
	UOperativeLibrary* L = Lib();
	const FOperativeClipInfo* Info = L ? L->FindClip(ClipId) : nullptr;
	if (!Info || !Info->Sequence) return false;
	if (bDeadOnce || State == EOperativeState::Dead || State == EOperativeState::Dying || State == EOperativeState::Respawning)
	{
		bDeadOnce = false;
		Health = 1.f;
		if (AOperativeCharacter* H = Host()) H->HostOnRespawn();
	}
	Disable = EDisableKind::None;
	if (State == EOperativeState::Action) CancelActionState(true);
	ClearUpper(0.f);
	if (State != EOperativeState::Viewer) SetState(EOperativeState::Viewer);
	Phase = 0;
	const FName Layer = Info->Layer;
	const bool bLoop = bForceLoop || Info->bLoop;
	if (Info->bAdditive)
	{
		// additive clips (hits) are shown over the stance idle
		PlayBase(StanceIdleClip(), 1.f, true, 0.15f);
		HitPlayer[0].bActive = false;
		StartPlayer(HitPlayer[0], ClipId, Rate, bForceLoop, StartTime, FName("hit0"));
		HitWeightScale[0] = 1.f;
	}
	else if (Layer == FName("upper"))
	{
		PlayBase(StanceIdleClip(), 1.f, true, 0.15f);
		UpperKind = ClipId == FName("cast_directional") ? EOperativeUpper::CastDirectional : ClipId == FName("ranged_burst") ? EOperativeUpper::RangedBurst : EOperativeUpper::RangedFire;
		StartPlayer(Upper, ClipId, Rate, bForceLoop, StartTime, FName("upper"));
		UpperTargetAlpha = 1.f;
	}
	else
	{
		PlayBase(ClipId, Rate, bLoop, 0.2f, StartTime);
		if (Info->bStaticPose) Base.bLoop = true;
	}
	return true;
}

void UOperativeActionComponent::StopViewer()
{
	if (State != EOperativeState::Viewer) return;
	HitPlayer[0].Reset();
	ClearUpper(0.f);
	EnterLocomotion(0.25f);
}

void UOperativeActionComponent::SetViewerPaused(bool b)
{
	Base.bPaused = b;
	Upper.bPaused = b;
	HitPlayer[0].bPaused = b;
}

void UOperativeActionComponent::SeekViewer(float Time)
{
	FOperativePlayer* P = Base.Info && (Base.Info->Layer == FName("full") || Base.Info->Layer == FName("pose")) ? &Base : (Upper.bActive ? &Upper : &HitPlayer[0]);
	if (!P->bActive) return;
	P->Time = FMath::Clamp(Time, 0.f, P->Length);
	P->NextEvent = 0;
	while (P->Events && P->NextEvent < P->Events->Num() && (*P->Events)[P->NextEvent].TimeS <= P->Time) ++P->NextEvent;
}
