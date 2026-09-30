// Autopilot of the extra Operatives (instance toggle): a varied but deterministic loop of locomotion and actions, using the same
// public API as the player, so ten characters exercise the complete controller at once.
#include "OperativeCharacter.h"
#include "OperativeActionComponent.h"
#include "ShowcaseRoom.h"
#include "EngineUtils.h"

void AOperativeCharacter::TickAutopilot(float Dt)
{
	if (!Actions) return;
	if (!bApInit)
	{
		bApInit = true;
		ApRandom.Initialize(AutopilotSeed);
		ApHome = GetActorLocation();
		ApTimer = ApRandom.FRandRange(0.2f, 1.5f);
		Actions->SetFacingMode(EOperativeFacingMode::Aim);
	}
	// aim target: the nearest showcase target so shots hit something
	AShowcaseTarget* Nearest = nullptr;
	float Best = TNumericLimits<float>::Max();
	for (TActorIterator<AShowcaseTarget> It(GetWorld()); It; ++It)
	{
		const float D = FVector::DistSquared(It->GetActorLocation(), GetActorLocation());
		if (D < Best) { Best = D; Nearest = *It; }
	}
	FVector AimAt = Nearest ? Nearest->GetActorLocation() + FVector(0.f, 0.f, Nearest->GetHeight()) : GetActorLocation() + GetActorForwardVector() * 400.f;
	// keep the aim target ahead of the walking direction while moving
	if (!ApTarget.IsNearlyZero() && ApSpeed > 0.f && (ApMode == 0 || ApMode == 1))
	{
		FVector D = (ApTarget - GetActorLocation()).GetSafeNormal2D();
		AimAt = GetActorLocation() + D * 400.f + FVector(0.f, 0.f, 60.f);
	}
	SetAimPoint(AimAt);

	// walking towards the wander target
	if (ApSpeed > 0.f)
	{
		FVector To = ApTarget - GetActorLocation();
		To.Z = 0.f;
		if (To.Size() < 60.f) { ApSpeed = 0.f; SetMoveIntent(FVector::ZeroVector, 0.f); }
		else SetMoveIntent(To, ApSpeed);
	}
	if (bApChannel)
	{
		ApChannelTimer -= Dt;
		if (ApChannelTimer <= 0.f) { bApChannel = false; Actions->RequestChannelRelease(); }
	}
	ApTimer -= Dt;
	if (ApTimer > 0.f) return;

	if (!Actions->IsAlive())
	{
		if (Actions->GetState() == EOperativeState::Dead) Actions->Respawn();
		ApTimer = 1.f;
		return;
	}
	// choose the next behaviour
	const int32 Pick = ApRandom.RandRange(0, 15);
	ApMode = Pick;
	ApTimer = ApRandom.FRandRange(1.6f, 3.4f);
	auto Wander = [&](float Speed)
	{
		const FVector2D Off(ApRandom.FRandRange(-260.f, 260.f), ApRandom.FRandRange(-260.f, 260.f));
		ApTarget = ApHome + FVector(Off.X, Off.Y, 0.f);
		ApSpeed = Speed;
	};
	switch (Pick)
	{
	case 0: case 1: Wander(150.f); ApMode = 0; break;
	case 2: case 3: Wander(400.f); ApMode = 1; ApTimer = 2.5f; break;
	case 4: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->SetAimHold(true); Actions->RequestFire(); ApTimer = 1.2f; break;
	case 5: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestBurst(); ApTimer = 1.6f; break;
	case 6: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestMelee(); ApTimer = 1.6f; break;
	case 7: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestCastGround(); ApTimer = 2.2f; break;
	case 8: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; if (Actions->RequestChannelStart()) { bApChannel = true; ApChannelTimer = 1.6f; ApTimer = 3.0f; } break;
	case 9: Actions->ApplyHit(FRotator(0.f, ApRandom.FRandRange(0.f, 360.f), 0.f).Vector(), 0.f); ApTimer = 0.9f; break;
	case 10: Actions->RequestDash(FRotator(0.f, ApRandom.FRandRange(0.f, 360.f), 0.f).Vector()); ApTimer = 1.4f; break;
	case 11: Actions->RequestJump(); ApTimer = 1.6f; break;
	case 12: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestReload(); ApTimer = 2.6f; break;
	case 13: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestEmote(EOperativeAction::Greet); ApTimer = 2.8f; break;
	case 14: SetMoveIntent(FVector::ZeroVector, 0.f); ApSpeed = 0.f; Actions->RequestCastSelf(); ApTimer = 1.6f; break;
	default: Wander(150.f); ApMode = 0; break;
	}
}
