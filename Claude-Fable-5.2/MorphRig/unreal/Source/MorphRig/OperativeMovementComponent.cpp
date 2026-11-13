#include "OperativeMovementComponent.h"

void UOperativeMovementComponent::CalcVelocity(float DeltaTime, float Friction, bool bFluid, float BrakingDeceleration)
{
	if (bForcedVelocity)
	{
		Velocity.X = ForcedVelocity.X;
		Velocity.Y = ForcedVelocity.Y;
		return;
	}
	Super::CalcVelocity(DeltaTime, Friction, bFluid, BrakingDeceleration);
}
