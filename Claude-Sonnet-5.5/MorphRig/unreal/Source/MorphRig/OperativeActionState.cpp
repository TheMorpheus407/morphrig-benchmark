// UOperativeActionComponent, part 2: per state updates, locomotion blend and pose recipe.
#include "OperativeActionComponent.h"
#include "OperativeLibrary.h"
#include "OperativeCharacter.h"
#include "OperativeFaceComponent.h"
#include "Animation/AnimSequence.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/SkeletalMeshComponent.h"

namespace
{
	inline float Smooth01(float X) { X = FMath::Clamp(X, 0.f, 1.f); return X * X * (3.f - 2.f * X); }
	inline float YawOf(const FVector& V) { return FMath::RadiansToDegrees(FMath::Atan2(V.Y, V.X)); }
}

void UOperativeActionComponent::SetMoveInput(const FVector& WorldDir, float DesiredSpeedCmS)
{
	FVector D = WorldDir;
	D.Z = 0.f;
	MoveDir = D.GetSafeNormal();
	DesiredSpeed = DesiredSpeedCmS;
}

void UOperativeActionComponent::SetAimTarget(const FVector& WorldPoint, bool bHasTarget)
{
	AimTarget = WorldPoint;
	bHasAimTarget = bHasTarget;
}

float UOperativeActionComponent::ComputeDesiredYaw(float Speed) const
{
	const AOperativeCharacter* H = Host();
	const float Cur = H->GetActorRotation().Yaw;
	switch (FacingMode)
	{
	case EOperativeFacingMode::Aim:
	{
		if (bHasAimTarget)
		{
			FVector To = AimTarget - H->GetActorLocation();
			To.Z = 0.f;
			if (To.SizeSquared() > 25.f) return YawOf(To);
		}
		return Cur;
	}
	case EOperativeFacingMode::Movement:
	{
		if (!MoveDir.IsNearlyZero() && DesiredSpeed > 5.f && !bRooted) return YawOf(MoveDir);
		const FVector V = H->GetVelocity();
		if (Speed > 60.f) return YawOf(FVector(V.X, V.Y, 0.f));
		return Cur;
	}
	default:
		return Cur;
	}
}

// ------------------------------------------------------------------------------------------------ main update

void UOperativeActionComponent::UpdateActions(float DtIn)
{
	AOperativeCharacter* H = Host();
	if (!H) return;
	if (!Library.IsValid())
	{
		Library = UOperativeLibrary::Get(this);
		if (!Library.IsValid()) return;
	}
	if (!Lib()->IsReady()) return;
	if (Base.ClipId.IsNone() && !Base.bActive)
	{
		PlayBase(StanceIdleClip(), 1.f, true, 0.f);
	}
	LocalTime += DtIn;
	const float Dt = bStasis ? 0.f : DtIn;
	Out = FHostOutput();
	const FVector Vel = H->GetVelocity();
	const float Speed = FVector(Vel.X, Vel.Y, 0.f).Size();
	DesiredFacingYaw = ComputeDesiredYaw(Speed);
	Out.DesiredYaw = DesiredFacingYaw;
	Out.TurnRateDegS = FacingMode == EOperativeFacingMode::Movement ? 540.f : 720.f;

	if (IsGrounded()) NotGroundedTime = 0.f; else NotGroundedTime += DtIn;
	AimHoldTimer = FMath::Max(0.f, AimHoldTimer - Dt);
	CombatTimer = FMath::Max(0.f, CombatTimer - Dt);
	if (SnapshotDuration > 0.f) SnapshotElapsed += Dt;
	if (State != EOperativeState::Locomotion && State != EOperativeState::Viewer && Upper.bActive) ClearUpper(0.f);

	if (bStasis)
	{
		Out.MoveSpeedScale = 0.f;
		Out.bBrakeToStop = true;
	}
	switch (State)
	{
	case EOperativeState::Locomotion: UpdateLocomotion(Dt); break;
	case EOperativeState::Airborne: UpdateAirborne(Dt); break;
	case EOperativeState::Dash: UpdateDash(Dt); break;
	case EOperativeState::Blink: UpdateBlink(Dt); break;
	case EOperativeState::Action: UpdateAction(Dt); break;
	case EOperativeState::Stun:
	case EOperativeState::Sleep:
	case EOperativeState::Knockback:
	case EOperativeState::Knockup:
	case EOperativeState::Knockdown: UpdateDisable(Dt); break;
	case EOperativeState::Dying:
	case EOperativeState::Dead:
	case EOperativeState::Respawning: UpdateDeath(Dt); break;
	case EOperativeState::Viewer: UpdateViewer(Dt); break;
	}
	UpdateUpper(Dt);
	UpdateHits(Dt);
	UpdateAimLook(Dt);
	BuildRecipe(Dt);
}

// ------------------------------------------------------------------------------------------------ locomotion

void UOperativeActionComponent::EnterLocomotion(float BlendTime, bool bKeepPhase)
{
	SetState(EOperativeState::Locomotion);
	Action = EOperativeAction::None;
	Disable = EDisableKind::None;
	LocoSub = ELocoSub::Idle;
	IdleTime = 0.f;
	bControlReturned = true;
	PlayBase(StanceIdleClip(), 1.f, true, BlendTime);
}

FName UOperativeActionComponent::PickLocoDominant() const
{
	FName Best;
	float BestW = -1.f;
	for (const FLocoBlendEntry& E : LocoBlend)
	{
		if (E.Info && E.Weight > BestW) { BestW = E.Weight; Best = E.Info->Id; }
	}
	return Best;
}

void UOperativeActionComponent::ComputeLocoBlend(float Theta, float Speed)
{
	UOperativeLibrary* L = Lib();
	LocoBlend.Reset();
	// direction sectors ordered by signed angle (left positive): b(-180) br(-135) r(-90) fr(-45) f(0) fl(45) l(90) bl(135) b(180)
	static const TCHAR* Order[9] = { TEXT("b"), TEXT("br"), TEXT("r"), TEXT("fr"), TEXT("f"), TEXT("fl"), TEXT("l"), TEXT("bl"), TEXT("b") };
	const float T = FMath::Clamp((Theta + 180.f) / 45.f, 0.f, 7.9999f);
	const int32 K = (int32)T;
	const float Frac = T - K;
	float WRun = Smooth01((Speed - 210.f) / 80.f);
	const float WSprint = Smooth01((Speed - 470.f) / 130.f) * FMath::Clamp(1.f - (FMath::Abs(Theta) - 40.f) / 40.f, 0.f, 1.f);
	WRun *= (1.f - WSprint);
	const float WWalk = FMath::Max(0.f, 1.f - WRun - WSprint);
	auto Add = [&](const FString& Name, float W)
	{
		if (W <= 1e-3f) return;
		const FOperativeClipInfo* Info = L->FindClip(FName(*Name));
		if (!Info || !Info->Sequence) return;
		for (FLocoBlendEntry& E : LocoBlend)
		{
			if (E.Info == Info) { E.Weight += W; return; }
		}
		FLocoBlendEntry E;
		E.Info = Info;
		E.Weight = W;
		LocoBlend.Add(E);
	};
	const struct { const TCHAR* Prefix; float W; } Gaits[2] = { { TEXT("walk"), WWalk }, { TEXT("run"), WRun } };
	for (const auto& G : Gaits)
	{
		Add(FString::Printf(TEXT("%s_%s"), G.Prefix, Order[K]), G.W * (1.f - Frac));
		Add(FString::Printf(TEXT("%s_%s"), G.Prefix, Order[K + 1]), G.W * Frac);
	}
	Add(TEXT("sprint_f"), WSprint);
	float Sum = 0.f, Stride = 0.f;
	for (const FLocoBlendEntry& E : LocoBlend)
	{
		Sum += E.Weight;
		Stride += E.Weight * FMath::Max(E.Info->StrideCm(), 20.f);
	}
	if (Sum > 1e-4f)
	{
		for (FLocoBlendEntry& E : LocoBlend) E.Weight /= Sum;
		LocoStrideCm = Stride / Sum;
	}
	else
	{
		LocoStrideCm = 165.f;
	}
}

void UOperativeActionComponent::SetPlayerPhase(FOperativePlayer& P, float NewNormalized)
{
	if (!P.bActive) return;
	const float NewTime = FMath::Clamp(NewNormalized, 0.f, 0.99999f) * P.Length;
	float DtEq = NewTime - P.Time;
	if (DtEq < -0.5f * P.Length) DtEq += P.Length;   // wrapped
	if (DtEq > 0.f)
	{
		const float SavedRate = P.Rate;
		P.Rate = 1.f;
		AdvancePlayer(P, DtEq);
		P.Rate = SavedRate;
	}
}

void UOperativeActionComponent::StartLocoMove(bool bMatchPhase, float BlendTime)
{
	AOperativeCharacter* H = Host();
	UOperativeLibrary* L = Lib();
	const FVector Vel = H->GetVelocity();
	const float Speed = FVector(Vel.X, Vel.Y, 0.f).Size();
	const FVector DirVec = Speed > 25.f ? FVector(Vel.X, Vel.Y, 0.f) : MoveDir;
	LocoThetaSmoothed = RelativeAngleLeft(DirVec);
	// reference feet from the pose that is leaving
	FVector RefL = FVector::ZeroVector, RefR = FVector::ZeroVector;
	bool bRef = false;
	if (bMatchPhase && Base.bActive && Base.Info && Base.Info->Layer != FName("pose")) bRef = L->GetFootPositions(Base.ClipId, Base.Time, RefL, RefR);
	const float SpeedForBlend = FMath::Max(Speed, FMath::Min(DesiredSpeed, 200.f));
	ComputeLocoBlend(LocoThetaSmoothed, SpeedForBlend);
	const FName Dominant = PickLocoDominant();
	if (Dominant.IsNone())
	{
		EnterLocomotion(BlendTime);
		return;
	}
	LocoPhase = bRef ? L->MatchLoopPhase(Dominant, RefL, RefR) : 0.f;
	LocoSub = ELocoSub::Move;
	RequestSnapshot(BlendTime);
	const float Len = L->GetClipLength(Dominant);
	StartPlayer(Base, Dominant, 1.f, true, LocoPhase * Len, FName("base"));
	LastMoveClipDominant = Dominant;
}

void UOperativeActionComponent::UpdateLocomotion(float Dt)
{
	AOperativeCharacter* H = Host();
	UOperativeLibrary* L = Lib();
	const FVector Vel = H->GetVelocity();
	const float Speed = FVector(Vel.X, Vel.Y, 0.f).Size();
	const bool bInput = !MoveDir.IsNearlyZero() && DesiredSpeed > 5.f && !bRooted;
	const float FacingYaw = H->GetActorRotation().Yaw;

	if (NotGroundedTime > 0.12f)
	{
		EnterAirborne(false);
		return;
	}

	switch (LocoSub)
	{
	case ELocoSub::Idle:
	{
		IdleTime += Dt;
		const FName Want = StanceIdleClip();
		if (Base.ClipId != Want)
		{
			PlayBase(Want, 1.f, true, 0.35f);
		}
		else
		{
			AdvancePlayer(Base, Dt);
		}
		const float Err = FMath::FindDeltaAngleDegrees(FacingYaw, DesiredFacingYaw);
		if (bInput || Speed > 40.f)
		{
			const float Theta = RelativeAngleLeft(bInput ? MoveDir : FVector(Vel.X, Vel.Y, 0.f));
			if (bInput && IdleTime > 0.15f && FMath::Abs(Theta) < 55.f && DesiredSpeed >= 90.f && Speed < 60.f)
			{
				LocoSub = ELocoSub::Start;
				PlayBase(FName("start_f"), 1.f, false, 0.12f);
			}
			else
			{
				StartLocoMove(true, 0.18f);
			}
		}
		else if (FacingMode != EOperativeFacingMode::Locked && FMath::Abs(Err) > 75.f && IdleTime > 0.1f && !bStasis)
		{
			LocoSub = ELocoSub::Turn;
			TurnStartYaw = FacingYaw;
			TurnTargetYaw = FacingYaw + FMath::Clamp(Err, -135.f, 135.f);
			PlayBase(Err < 0.f ? FName("turn_l90") : FName("turn_r90"), ActionRate, false, 0.15f);
		}
		break;
	}
	case ELocoSub::Start:
	{
		AdvancePlayer(Base, Dt);
		const float Theta = RelativeAngleLeft(bInput ? MoveDir : FVector(Vel.X, Vel.Y, 0.f));
		if (!bInput && Speed < 25.f)
		{
			EnterLocomotion(0.2f);
		}
		else if (Base.bFinished || FMath::Abs(Theta) > 70.f)
		{
			StartLocoMove(true, 0.2f);
		}
		break;
	}
	case ELocoSub::Move:
	{
		const FVector DirVec = Speed > 25.f ? FVector(Vel.X, Vel.Y, 0.f) : MoveDir;
		const float ThetaTarget = RelativeAngleLeft(DirVec);
		const float Delta = FMath::FindDeltaAngleDegrees(LocoThetaSmoothed, ThetaTarget);
		LocoThetaSmoothed = FRotator::NormalizeAxis(LocoThetaSmoothed + FMath::Clamp(Delta, -720.f * Dt, 720.f * Dt));
		LocoSpeedSmoothed = Speed;
		ComputeLocoBlend(LocoThetaSmoothed, Speed);
		// switch the displayed dominant clip (events) with hysteresis
		const FName Dominant = PickLocoDominant();
		if (!Dominant.IsNone() && Dominant != Base.ClipId)
		{
			float CurW = 0.f, NewW = 0.f;
			for (const FLocoBlendEntry& E : LocoBlend)
			{
				if (E.Info->Id == Base.ClipId) CurW = E.Weight;
				if (E.Info->Id == Dominant) NewW = E.Weight;
			}
			if (NewW > CurW + 0.15f || CurW <= 0.f)
			{
				const float Len = L->GetClipLength(Dominant);
				StartPlayer(Base, Dominant, 1.f, true, LocoPhase * Len, FName("base"));
			}
		}
		const float Advance = Speed * Dt / FMath::Max(LocoStrideCm, 20.f);
		LocoPhase = FMath::Fmod(LocoPhase + Advance, 1.f);
		SetPlayerPhase(Base, LocoPhase);
		if (!bInput)
		{
			if (Speed > 90.f && FMath::Abs(LocoThetaSmoothed) < 75.f && !bStasis)
			{
				LocoSub = ELocoSub::Stop;
				PlayBase(FName("stop_f"), 1.f, false, 0.15f);
			}
			else if (Speed < 25.f)
			{
				EnterLocomotion(0.25f);
			}
		}
		else if (FacingMode == EOperativeFacingMode::Movement && Speed > 150.f && !bStasis)
		{
			const float Err = FMath::FindDeltaAngleDegrees(FacingYaw, DesiredFacingYaw);
			if (FMath::Abs(Err) > 150.f)
			{
				LocoSub = ELocoSub::Pivot;
				TurnStartYaw = FacingYaw;
				TurnTargetYaw = FacingYaw + (Err < 0.f ? -180.f : 180.f);
				PlayBase(Err < 0.f ? FName("pivot_l180") : FName("pivot_r180"), 1.f, false, 0.10f);
			}
		}
		break;
	}
	case ELocoSub::Stop:
	{
		AdvancePlayer(Base, Dt);
		Out.bBrakeToStop = true;
		if (bInput)
		{
			StartLocoMove(true, 0.15f);
		}
		else if (Base.bFinished || (Speed < 8.f && Base.Time > 0.5f * Base.Length))
		{
			EnterLocomotion(0.2f);
		}
		break;
	}
	case ELocoSub::Turn:
	{
		AdvancePlayer(Base, Dt);
		const float Progress = Base.Length > 1e-3f ? Base.Time / Base.Length : 1.f;
		Out.bFacingDriven = true;
		Out.DrivenYaw = FMath::Lerp(TurnStartYaw, TurnTargetYaw, Smooth01(Progress));
		Out.MoveSpeedScale = 0.f;
		if (bInput && Progress > 0.3f)
		{
			StartLocoMove(true, 0.15f);
		}
		else if (Base.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	}
	case ELocoSub::Pivot:
	{
		AdvancePlayer(Base, Dt);
		const float Progress = Base.Length > 1e-3f ? Base.Time / Base.Length : 1.f;
		Out.bFacingDriven = true;
		Out.DrivenYaw = FMath::Lerp(TurnStartYaw, TurnTargetYaw, Smooth01(Progress));
		Out.MoveSpeedScale = 0.55f;
		if (Base.bFinished) StartLocoMove(true, 0.2f);
		break;
	}
	}
	if (bRooted) Out.MoveSpeedScale = 0.f;
}

// ------------------------------------------------------------------------------------------------ airborne

void UOperativeActionComponent::EnterAirborne(bool bFromJump)
{
	if (State == EOperativeState::Action) CancelActionState(false);
	ClearUpper(0.f);
	SetState(EOperativeState::Airborne);
	AirTime = 0.f;
	MinZVel = 0.f;
	bJumpTookOff = false;
	AirSub = EAirSub::JumpAir;
	PlayBase(FName("jump_air"), 1.f, true, 0.15f);
}

void UOperativeActionComponent::UpdateAirborne(float Dt)
{
	AOperativeCharacter* H = Host();
	const float ZVel = H->GetVelocity().Z;
	AirTime += Dt;
	MinZVel = FMath::Min(MinZVel, ZVel);
	const bool bGrounded = IsGrounded();
	Out.bAirControl = true;
	switch (AirSub)
	{
	case EAirSub::JumpStart:
		AdvancePlayer(Base, Dt);
		Out.MoveSpeedScale = 0.f;
		Out.bBrakeToStop = false;
		if (Base.bFinished)
		{
			if (!bJumpTookOff) { H->HostJump(); bJumpTookOff = true; }
			AirSub = EAirSub::JumpAir;
			PlayBase(FName("jump_air"), 1.f, true, 0.12f);
		}
		else if (bJumpTookOff && bGrounded && AirTime > 0.6f)
		{
			// took off but landed before the clip ended (very low ceiling): drop into the landing
			AirSub = EAirSub::Land;
			PlayBase(FName("jump_land"), ActionRate, false, 0.08f);
		}
		break;
	case EAirSub::JumpAir:
	case EAirSub::Fall:
	{
		AdvancePlayer(Base, Dt);
		if (bGrounded && AirTime > 0.08f)
		{
			const float FallSpeed = -MinZVel;
			const bool bHeavy = FallSpeed > 800.f || AirTime > 1.6f;
			AirSub = bHeavy ? EAirSub::LandHeavy : EAirSub::Land;
			PlayBase(bHeavy ? FName("land_heavy") : FName("jump_land"), ActionRate, false, 0.08f);
			bControlReturned = false;
		}
		else if (AirSub == EAirSub::JumpAir && (AirTime > 0.9f || ZVel < -900.f))
		{
			AirSub = EAirSub::Fall;
			PlayBase(FName("fall"), 1.f, true, 0.2f);
		}
		break;
	}
	case EAirSub::Land:
	case EAirSub::LandHeavy:
	{
		AdvancePlayer(Base, Dt);
		const bool bInput = !MoveDir.IsNearlyZero() && DesiredSpeed > 5.f && !bRooted;
		Out.MoveSpeedScale = bControlReturned ? 1.f : (AirSub == EAirSub::LandHeavy ? 0.f : 0.35f);
		Out.bBrakeToStop = !bControlReturned && AirSub == EAirSub::LandHeavy;
		if (Base.bFinished || (bControlReturned && bInput))
		{
			EnterLocomotion(0.2f);
		}
		break;
	}
	}
}

// ------------------------------------------------------------------------------------------------ dash, blink

FVector UOperativeActionComponent::RootDelta(const FOperativeClipInfo* Info, float T0, float T1) const
{
	if (!Info || !Info->Sequence) return FVector::ZeroVector;
	FTransform R0, R1;
	Info->Sequence->GetBoneTransform(R0, FSkeletonPoseBoneIndex(0), FAnimExtractContext((double)T0, false), false);
	Info->Sequence->GetBoneTransform(R1, FSkeletonPoseBoneIndex(0), FAnimExtractContext((double)T1, false), false);
	return R1.GetTranslation() - R0.GetTranslation();
}

void UOperativeActionComponent::UpdateDash(float Dt)
{
	AOperativeCharacter* H = Host();
	const float Prev = Base.Time;
	AdvancePlayer(Base, Dt);
	const float Cur = Base.Time;
	const FVector Local = RootDelta(Base.Info, Prev, Cur);
	Out.RootMotionWorldDelta = FRotator(0.f, DashYaw, 0.f).RotateVector(Local);
	Out.bDashActive = true;
	Out.MoveSpeedScale = 0.f;
	Out.bFacingDriven = true;
	Out.DrivenYaw = DashYaw;
	if (Base.bFinished)
	{
		EnterLocomotion(0.12f);
	}
	else if (NotGroundedTime > 0.25f)
	{
		EnterAirborne(false);
	}
}

void UOperativeActionComponent::UpdateBlink(float Dt)
{
	AOperativeCharacter* H = Host();
	AdvancePlayer(Base, Dt);
	Out.MoveSpeedScale = 0.f;
	Out.bBrakeToStop = true;
	Out.bFacingDriven = true;
	Out.DrivenYaw = H->GetActorRotation().Yaw;
	if (Phase == 0)
	{
		if (Base.bFinished)
		{
			if (!bBlinkTeleported) { H->HostBlinkTeleport(BlinkDir, BlinkDist); bBlinkTeleported = true; }
			Phase = 1;
			PlayBase(FName("blink_in"), ActionRate, false, 0.f);
		}
	}
	else if (Base.bFinished)
	{
		H->HostSetMeshVisible(true);
		EnterLocomotion(0.1f);
	}
}

// ------------------------------------------------------------------------------------------------ actions

void UOperativeActionComponent::UpdateAction(float Dt)
{
	AOperativeCharacter* H = Host();
	const bool bInput = !MoveDir.IsNearlyZero() && DesiredSpeed > 5.f && !bRooted;
	AdvancePlayer(Base, Dt);
	if (State != EOperativeState::Action) return;   // an event handler may have changed the state
	Out.MoveSpeedScale = 0.f;
	Out.bBrakeToStop = true;
	Out.TurnRateDegS = 0.f;
	switch (Action)
	{
	case EOperativeAction::Melee:
	{
		Out.TurnRateDegS = 220.f;
		if (bComboQueued && ComboIndex < 3 && (bCancelWindow || bControlReturned))
		{
			++ComboIndex;
			bComboQueued = false;
			bCancelWindow = false;
			bControlReturned = false;
			bMeleeWindow = false;
			PlayBase(FName(*FString::Printf(TEXT("melee_%d"), ComboIndex)), ActionRate, false, 0.08f);
		}
		else if (Base.bFinished || (bControlReturned && bInput && !bComboQueued))
		{
			FinishAction(0.2f);
		}
		break;
	}
	case EOperativeAction::Reload:
	case EOperativeAction::CastGround:
	case EOperativeAction::CastSelf:
	case EOperativeAction::Deploy:
	case EOperativeAction::Greet:
	case EOperativeAction::Victory:
	case EOperativeAction::Defeat:
	case EOperativeAction::Dialogue:
	{
		if (Action == EOperativeAction::CastGround || Action == EOperativeAction::CastSelf) Out.TurnRateDegS = 120.f;
		if (Base.bFinished)
		{
			FinishAction(Action == EOperativeAction::Dialogue ? 0.25f : 0.2f);
		}
		else if (bControlReturned && bInput)
		{
			FinishAction(0.2f);
		}
		break;
	}
	case EOperativeAction::Channel:
	{
		Out.TurnRateDegS = 90.f;
		if (Phase <= 1)
		{
			if (bInterruptRequested)
			{
				Phase = 3;
				bChannelSustain = false;
				PlayBase(FName("channel_interrupt"), ActionRate, false, 0.08f);
			}
			else if (bReleaseRequested || (Phase == 1 && ActionTimer > 12.f))
			{
				Phase = 2;
				PlayBase(FName("channel_end"), ActionRate, false, 0.10f);
			}
			else if (Phase == 0 && Base.bFinished)
			{
				Phase = 1;
				ActionTimer = 0.f;
				PlayBase(FName("channel_loop"), ActionRate, true, 0.08f);
			}
			else if (Phase == 1)
			{
				ActionTimer += Dt;
			}
		}
		else if (Base.bFinished)
		{
			FinishAction(0.2f);
		}
		break;
	}
	case EOperativeAction::Charge:
	{
		Out.TurnRateDegS = 90.f;
		if (Phase <= 1)
		{
			ChargeTime += Dt * ActionRate;
			if (bCancelRequested || bInterruptRequested || (Phase == 1 && ChargeTime > 10.f))
			{
				Phase = 3;
				ChargeActive = false;
				PlayBase(FName("charge_cancel"), ActionRate, false, 0.08f);
			}
			else if (bReleaseRequested)
			{
				Phase = 2;
				ChargeActive = false;
				PlayBase(FName("charge_release"), ActionRate, false, 0.08f);
			}
			else if (Phase == 0 && Base.bFinished)
			{
				Phase = 1;
				PlayBase(FName("charge_hold"), ActionRate, true, 0.08f);
			}
		}
		else if (Base.bFinished)
		{
			ChargeTime = 0.f;
			FinishAction(0.2f);
		}
		break;
	}
	case EOperativeAction::Uplink:
	{
		if (Phase <= 1)
		{
			if (bCancelRequested || bInterruptRequested)
			{
				Phase = 3;
				PlayBase(FName("uplink_cancel"), ActionRate, false, 0.08f);
			}
			else if (Phase == 0 && Base.bFinished)
			{
				Phase = 1;
				ActionTimer = 0.f;
				PlayBase(FName("uplink_loop"), ActionRate, true, 0.08f);
			}
			else if (Phase == 1)
			{
				ActionTimer += Dt * ActionRate;
				if (ActionTimer >= UplinkDuration)
				{
					Phase = 2;
					PlayBase(FName("uplink_end"), ActionRate, false, 0.08f);
				}
			}
		}
		else if (Base.bFinished)
		{
			FinishAction(0.2f);
		}
		break;
	}
	default:
		FinishAction(0.1f);
		break;
	}
}

// ------------------------------------------------------------------------------------------------ disables

void UOperativeActionComponent::UpdateDisable(float Dt)
{
	AOperativeCharacter* H = Host();
	AdvancePlayer(Base, Dt);
	Out.MoveSpeedScale = 0.f;
	Out.bBrakeToStop = true;
	Out.TurnRateDegS = 0.f;
	Out.bAirControl = false;
	switch (State)
	{
	case EOperativeState::Stun:
		DisableTimer -= Dt;
		if (Phase == 0 && Base.bFinished)
		{
			if (DisableTimer <= 0.f) { Phase = 2; PlayBase(FName("stun_end"), ActionRate, false, 0.1f); }
			else { Phase = 1; PlayBase(FName("stun_loop"), ActionRate, true, 0.1f); }
		}
		else if (Phase == 1 && DisableTimer <= 0.f)
		{
			Phase = 2;
			PlayBase(FName("stun_end"), ActionRate, false, 0.1f);
		}
		else if (Phase == 2 && Base.bFinished)
		{
			EnterLocomotion(0.15f);
		}
		break;
	case EOperativeState::Sleep:
		if (Phase == 0 && Base.bFinished)
		{
			Phase = 1;
			PlayBase(FName("sleep_loop"), ActionRate, true, 0.1f);
		}
		else if (Phase == 1)
		{
			if (DisableTimer > 0.f)
			{
				DisableTimer -= Dt;
				if (DisableTimer <= 0.f) { Phase = 2; PlayBase(FName("sleep_end"), ActionRate, false, 0.15f); }
			}
		}
		else if (Phase == 2 && Base.bFinished)
		{
			EnterLocomotion(0.15f);
		}
		break;
	case EOperativeState::Knockback:
	{
		const float T = Base.Length / FMath::Max(Base.Rate, 0.1f);
		const float U = FMath::Clamp(Base.Time / FMath::Max(Base.Length, 1e-3f), 0.f, 1.f);
		const float V0 = 2.f * KnockDistance / FMath::Max(T, 0.1f);
		Out.KnockbackVelocity = KnockTravelDir * V0 * (1.f - U);
		Out.bKnockbackActive = !Base.bFinished;
		if (Base.bFinished) EnterLocomotion(0.15f);
		break;
	}
	case EOperativeState::Knockup:
	{
		if (Phase == 0)
		{
			if (Base.bFinished)
			{
				if (!bKnockLaunched)
				{
					bKnockLaunched = true;
					FVector V = KnockTravelDir * KnockDistance;
					V.Z = KnockLaunchSpeed;
					H->HostLaunch(V);
				}
				Phase = 1;
				DisableTimer = 0.f;
				PlayBase(FName("knockup_air"), ActionRate, true, 0.1f);
			}
		}
		else
		{
			DisableTimer += Dt;
			if (IsGrounded() && DisableTimer > 0.15f)
			{
				ToKnockdown(KnockTravelDir, 0.10f);
			}
		}
		break;
	}
	case EOperativeState::Knockdown:
		if (Phase == 0 && Base.bFinished)
		{
			Phase = 1;
			DisableTimer = 1.2f;
			PlayBase(bFaceDown ? FName("prone_front") : FName("prone_back"), ActionRate, true, 0.1f);
		}
		else if (Phase == 1)
		{
			DisableTimer -= Dt;
			if (DisableTimer <= 0.f)
			{
				Phase = 2;
				PlayBase(bFaceDown ? FName("getup_front") : FName("getup_back"), ActionRate, false, 0.1f);
			}
		}
		else if (Phase == 2 && Base.bFinished)
		{
			EnterLocomotion(0.15f);
		}
		break;
	default:
		break;
	}
}

void UOperativeActionComponent::UpdateDeath(float Dt)
{
	Out.MoveSpeedScale = 0.f;
	Out.bBrakeToStop = true;
	Out.TurnRateDegS = 0.f;
	switch (State)
	{
	case EOperativeState::Dying:
		AdvancePlayer(Base, Dt);
		if (Base.bFinished)
		{
			SetState(EOperativeState::Dead);
			PlayBase(bDeathFront ? FName("dead_front") : FName("dead_back"), 1.f, false, 0.06f);
			Base.bPaused = true;
		}
		break;
	case EOperativeState::Dead:
		DeathHoldTime += Dt;
		break;
	case EOperativeState::Respawning:
		AdvancePlayer(Base, Dt);
		if (Base.bFinished)
		{
			EnterLocomotion(0.2f);
		}
		break;
	default:
		break;
	}
}

void UOperativeActionComponent::UpdateViewer(float Dt)
{
	Out.MoveSpeedScale = 0.f;
	Out.bBrakeToStop = true;
	Out.TurnRateDegS = 0.f;
	if (Base.bActive && !Base.bPaused)
	{
		if (Base.Info && Base.Info->bStaticPose)
		{
			// static poses are held
		}
		else
		{
			AdvancePlayer(Base, Dt);
			if (Base.bFinished) Base.bPaused = false;   // hold the last frame of a one shot
		}
	}
}

// ------------------------------------------------------------------------------------------------ upper layer and hits

void UOperativeActionComponent::UpdateUpper(float Dt)
{
	if (!Upper.bActive)
	{
		UpperAlpha = FMath::FInterpConstantTo(UpperAlpha, 0.f, Dt > 0.f ? Dt : 0.f, 8.f);
		return;
	}
	AdvancePlayer(Upper, Dt);
	if (!Upper.bActive) return;
	const float Remaining = (Upper.Length - Upper.Time) / FMath::Max(Upper.Rate, 0.1f);
	UpperTargetAlpha = (Remaining < 0.12f && State != EOperativeState::Viewer) ? 0.f : 1.f;
	const float Speed = UpperTargetAlpha > UpperAlpha ? 1.f / 0.07f : 1.f / 0.12f;
	UpperAlpha = FMath::FInterpConstantTo(UpperAlpha, UpperTargetAlpha, Dt, Speed);
	if (Upper.bFinished && State != EOperativeState::Viewer)
	{
		if (bUpperQueued)
		{
			bUpperQueued = false;
			UpperKind = UpperQueuedKind;
			const FName Clip = UpperKind == EOperativeUpper::RangedFire ? FName("ranged_fire") : UpperKind == EOperativeUpper::RangedBurst ? FName("ranged_burst") : FName("cast_directional");
			StartPlayer(Upper, Clip, ActionRate, false, 0.f, FName("upper"));
			UpperTargetAlpha = 1.f;
			AimHoldTimer = 2.0f;
		}
		else
		{
			Upper.Reset();
			UpperKind = EOperativeUpper::None;
		}
	}
}

void UOperativeActionComponent::UpdateHits(float Dt)
{
	float Scale = 1.f;
	switch (State)
	{
	case EOperativeState::Knockdown: case EOperativeState::Knockup: case EOperativeState::Sleep: Scale = 0.35f; break;
	case EOperativeState::Dying: case EOperativeState::Dead: case EOperativeState::Respawning: Scale = 0.f; break;
	default: break;
	}
	for (int32 I = 0; I < 2; ++I)
	{
		FOperativePlayer& P = HitPlayer[I];
		if (!P.bActive) continue;
		if (State != EOperativeState::Viewer || !P.bLoop) AdvancePlayer(P, Dt);
		else AdvancePlayer(P, Dt);
		if (!P.bActive) continue;
		if (P.bFinished && State != EOperativeState::Viewer)
		{
			P.Reset();
		}
		HitWeightScale[I] = Scale;
	}
}

// ------------------------------------------------------------------------------------------------ aim and look

void UOperativeActionComponent::UpdateAimLook(float Dt)
{
	AOperativeCharacter* H = Host();
	const float FacingYaw = H->GetActorRotation().Yaw;
	const bool bStateAllowsAim = State == EOperativeState::Locomotion && LocoSub != ELocoSub::Turn && LocoSub != ELocoSub::Pivot;
	AimActive = bStateAllowsAim && (bAimAlways || bAimHold || AimHoldTimer > 0.f || Upper.bActive);
	if (Upper.bActive) AimHoldTimer = FMath::Max(AimHoldTimer, 0.5f);

	// aim angles relative to the body facing
	float TargetYaw = 0.f, TargetPitch = 0.f;
	if (bHasAimTarget)
	{
		const FVector Origin = H->GetAimOrigin();
		const FVector To = AimTarget - Origin;
		const float Dist2D = FVector(To.X, To.Y, 0.f).Size();
		if (Dist2D > 5.f)
		{
			TargetYaw = -FMath::FindDeltaAngleDegrees(FacingYaw, YawOf(To));
			TargetPitch = FMath::RadiansToDegrees(FMath::Atan2(To.Z, Dist2D));
		}
	}
	TargetYaw = FMath::Clamp(TargetYaw, -60.f, 60.f);
	TargetPitch = FMath::Clamp(TargetPitch, -35.f, 35.f);
	const float Rate = 14.f;
	AimYawSmoothed = FMath::FInterpTo(AimYawSmoothed, TargetYaw, Dt, Rate);
	AimPitchSmoothed = FMath::FInterpTo(AimPitchSmoothed, TargetPitch, Dt, Rate);
	AimYawRel = AimYawSmoothed;
	AimPitchRel = AimPitchSmoothed;
	const float Speed = AimActive ? 9.f : 12.f;
	AimReadyAlpha = FMath::FInterpTo(AimReadyAlpha, AimActive ? 1.f : 0.f, Dt, Speed);
	if (AimReadyAlpha < 0.002f) AimReadyAlpha = 0.f;
	AimOffsetAlpha = AimReadyAlpha;

	// look at: head and eyes
	const bool bLookState = (State == EOperativeState::Locomotion || State == EOperativeState::Airborne || State == EOperativeState::Stun ||
		(State == EOperativeState::Action && Action != EOperativeAction::Dialogue));
	const bool bWantLook = bLookState && (bLookEnabled || AimActive);
	LookAlpha = FMath::FInterpTo(LookAlpha, bWantLook ? 1.f : 0.f, Dt, 6.f);
	if (LookAlpha < 0.002f) LookAlpha = 0.f;
	if (bWantLook || LookAlpha > 0.f)
	{
		const FVector Target = bLookEnabled ? LookTarget : (bHasAimTarget ? AimTarget : H->GetActorLocation() + H->GetActorForwardVector() * 300.f);
		FTransform HeadT;
		const FVector Origin = H->GetSocketTransformSafe(FName("fx_head_top"), HeadT) ? HeadT.GetLocation() - FVector(0.f, 0.f, 12.f) : H->GetAimOrigin();
		const FVector To = Target - Origin;
		const float Dist2D = FVector(To.X, To.Y, 0.f).Size();
		float YawRel = 0.f, PitchRel = 0.f;
		if (Dist2D > 5.f)
		{
			YawRel = -FMath::FindDeltaAngleDegrees(FacingYaw, YawOf(To));
			PitchRel = FMath::RadiansToDegrees(FMath::Atan2(To.Z, Dist2D));
		}
		const float AimApplied = AimYawRel * AimReadyAlpha * 0.9f;
		const float TotalYaw = FMath::Clamp(YawRel - AimApplied, -120.f, 120.f);
		const float HeadYaw = FMath::Clamp(TotalYaw * 0.65f, -60.f, 60.f);
		const float EyeYaw = FMath::Clamp(TotalYaw - HeadYaw, -25.f, 25.f);
		const float HeadPitch = FMath::Clamp(PitchRel * 0.6f, -30.f, 30.f);
		const float EyePitch = FMath::Clamp(PitchRel - HeadPitch, -20.f, 20.f);
		LookYaw = FMath::FInterpTo(LookYaw, HeadYaw, Dt, 8.f);
		LookPitch = FMath::FInterpTo(LookPitch, HeadPitch, Dt, 8.f);
		if (UOperativeFaceComponent* F = H->Face.Get())
		{
			F->SetLookEyes(EyeYaw * LookAlpha, EyePitch * LookAlpha);
		}
	}
	else
	{
		LookYaw = FMath::FInterpTo(LookYaw, 0.f, Dt, 8.f);
		LookPitch = FMath::FInterpTo(LookPitch, 0.f, Dt, 8.f);
		if (UOperativeFaceComponent* F = H->Face.Get()) F->SetLookEyes(0.f, 0.f);
	}
}

// ------------------------------------------------------------------------------------------------ recipe

void UOperativeActionComponent::AddSingleSample(FOperativePoseRecipe& R, const FOperativePlayer& P, float Weight)
{
	if (!P.bActive || !P.Info || !P.Info->Sequence) return;
	FOperativeSample S;
	S.Seq = P.Info->Sequence;
	S.Time = FMath::Clamp(P.Time, 0.f, P.Length);
	S.Weight = Weight;
	S.bLooping = P.bLoop;
	S.bLockRootXY = true;
	S.bRootMotionClip = P.Info->bRootMotion && P.Info->Sequence->bEnableRootMotion;
	R.Base.Add(S);
}

void UOperativeActionComponent::AddLocoSamples(FOperativePoseRecipe& R)
{
	for (const FLocoBlendEntry& E : LocoBlend)
	{
		if (!E.Info || !E.Info->Sequence) continue;
		FOperativeSample S;
		S.Seq = E.Info->Sequence;
		S.Time = LocoPhase * FMath::Max(E.Info->Length(), 1e-3f);
		S.Weight = E.Weight;
		S.bLooping = true;
		S.bLockRootXY = true;
		R.Base.Add(S);
	}
}

void UOperativeActionComponent::BuildRecipe(float Dt)
{
	AOperativeCharacter* H = Host();
	FOperativePoseRecipe R;
	R.SecondaryResetSerial = Recipe.SecondaryResetSerial;

	if (State == EOperativeState::Locomotion && LocoSub == ELocoSub::Move && LocoBlend.Num() > 0)
	{
		AddLocoSamples(R);
	}
	else
	{
		AddSingleSample(R, Base, 1.f);
	}
	R.SnapshotSerial = SnapshotSerial;
	if (SnapshotDuration > 0.f)
	{
		const float U = FMath::Clamp(1.f - SnapshotElapsed / SnapshotDuration, 0.f, 1.f);
		R.SnapshotAlpha = U * U * (3.f - 2.f * U);
	}

	if (Upper.bActive && Upper.Info && Upper.Info->Sequence)
	{
		R.Upper.Seq = Upper.Info->Sequence;
		R.Upper.Time = FMath::Clamp(Upper.Time, 0.f, Upper.Length);
		R.Upper.Weight = 1.f;
		R.Upper.bLooping = Upper.bLoop;
		R.Upper.bLockRootXY = true;
		R.UpperAlpha = UpperAlpha;
	}
	R.AimReadyAlpha = AimReadyAlpha;
	R.AimOffsetAlpha = AimOffsetAlpha;
	R.AimYaw = AimYawRel;
	R.AimPitch = AimPitchRel;
	for (int32 I = 0; I < 2; ++I)
	{
		const FOperativePlayer& P = HitPlayer[I];
		if (!P.bActive || !P.Info || !P.Info->Sequence) continue;
		R.Hit[I].Seq = P.Info->Sequence;
		R.Hit[I].Time = FMath::Clamp(P.Time, 0.f, P.Length);
		R.Hit[I].Weight = 1.f;
		R.Hit[I].bLooping = P.bLoop;
		const float N = P.Length > 1e-3f ? P.Time / P.Length : 0.f;
		const float Fade = 1.f - Smooth01((N - 0.6f) / 0.4f);
		R.HitWeight[I] = Fade * HitWeightScale[I];
	}
	R.LookAlpha = LookAlpha;
	R.HeadYaw = LookYaw;
	R.HeadPitch = LookPitch;
	if (const UOperativeFaceComponent* F = H->Face.Get()) R.Face = F->GetState();

	// foot IK is meaningful for standing, grounded states
	bool bIKState = false;
	switch (State)
	{
	case EOperativeState::Locomotion: bIKState = true; break;
	case EOperativeState::Airborne: bIKState = (AirSub == EAirSub::Land || AirSub == EAirSub::LandHeavy || AirSub == EAirSub::JumpStart); break;
	case EOperativeState::Action: bIKState = true; break;
	case EOperativeState::Stun: bIKState = true; break;
	case EOperativeState::Blink: bIKState = true; break;
	default: break;
	}
	const bool bWantIK = bIKEnabled && bIKState && bFootIKInput;
	R.bFootIK = bIKEnabled && bFootIKInput;
	// alpha smoothing lives here so the value is deterministic per update
	FootIKAlphaState = FMath::FInterpTo(FootIKAlphaState, bWantIK ? 1.f : 0.f, Dt > 0.f ? Dt : 0.f, 8.f);
	R.FootIKAlpha = FootIKAlphaState;
	R.PelvisOffset = PelvisOffsetInput;
	R.Foot[0] = FootInput[0];
	R.Foot[1] = FootInput[1];
	R.bSecondary = bSecondaryEnabled;
	R.SecondaryScale = 1.f;
	Recipe = MoveTemp(R);
}
