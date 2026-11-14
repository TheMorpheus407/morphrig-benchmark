// Copyright Epic Games, Inc. All Rights Reserved.

#include "MorphRigAnimInstance.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

static const TArray<FString>& AllClipIds()
{
	static TArray<FString> Ids = {
		TEXT("idle_relaxed"), TEXT("idle_combat"), TEXT("idle_wounded"),
		TEXT("walk_f"), TEXT("walk_fl"), TEXT("walk_l"), TEXT("walk_bl"), TEXT("walk_b"), TEXT("walk_br"), TEXT("walk_r"), TEXT("walk_fr"),
		TEXT("run_f"), TEXT("run_fl"), TEXT("run_l"), TEXT("run_bl"), TEXT("run_b"), TEXT("run_br"), TEXT("run_r"), TEXT("run_fr"),
		TEXT("sprint_f"), TEXT("start_f"), TEXT("stop_f"), TEXT("turn_l90"), TEXT("turn_r90"),
		TEXT("pivot_l180"), TEXT("pivot_r180"), TEXT("jump_start"), TEXT("jump_air"), TEXT("jump_land"),
		TEXT("fall"), TEXT("land_heavy"),
		TEXT("dash_f"), TEXT("dash_b"), TEXT("dash_l"), TEXT("dash_r"), TEXT("blink_out"), TEXT("blink_in"),
		TEXT("melee_1"), TEXT("melee_2"), TEXT("melee_3"),
		TEXT("ranged_fire"), TEXT("ranged_burst"), TEXT("reload"),
		TEXT("cast_directional"), TEXT("cast_ground"), TEXT("cast_self"),
		TEXT("channel_start"), TEXT("channel_loop"), TEXT("channel_end"), TEXT("channel_interrupt"),
		TEXT("charge_start"), TEXT("charge_hold"), TEXT("charge_release"), TEXT("charge_cancel"),
		TEXT("deploy"), TEXT("uplink_start"), TEXT("uplink_loop"), TEXT("uplink_end"), TEXT("uplink_cancel"),
		TEXT("hit_f"), TEXT("hit_b"), TEXT("hit_l"), TEXT("hit_r"),
		TEXT("stun_start"), TEXT("stun_loop"), TEXT("stun_end"), TEXT("knockback"),
		TEXT("knockup_start"), TEXT("knockup_air"), TEXT("knockdown_front"), TEXT("knockdown_back"),
		TEXT("prone_front"), TEXT("prone_back"), TEXT("getup_front"), TEXT("getup_back"),
		TEXT("sleep_start"), TEXT("sleep_loop"), TEXT("sleep_end"),
		TEXT("death_front"), TEXT("death_back"), TEXT("dead_front"), TEXT("dead_back"),
		TEXT("respawn"), TEXT("greet"), TEXT("victory"), TEXT("defeat"), TEXT("dialogue"),
		TEXT("aim_down_left"), TEXT("aim_down_center"), TEXT("aim_down_right"),
		TEXT("aim_level_left"), TEXT("aim_level_center"), TEXT("aim_level_right"),
		TEXT("aim_up_left"), TEXT("aim_up_center"), TEXT("aim_up_right")
	};
	return Ids;
}

static FString DirectionSuffix(float AngleDeg)
{
	// Angle relative to facing: 0=forward, +90=left, -90=right
	float A = FMath::Abs(AngleDeg);
	float S = FMath::Sign(AngleDeg);
	if (A < 22.5f) return TEXT("f");
	if (A < 67.5f) return S > 0 ? TEXT("fl") : TEXT("fr");
	if (A < 112.5f) return S > 0 ? TEXT("l") : TEXT("r");
	if (A < 157.5f) return S > 0 ? TEXT("bl") : TEXT("br");
	return TEXT("b");
}

void UMorphRigAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	EnsureLibrary();
}

void UMorphRigAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	EnsureLibrary();

	if (APawn* Pawn = TryGetPawnOwner())
	{
		if (ACharacter* Ch = Cast<ACharacter>(Pawn))
		{
			MoveInput = FVector2D(Ch->GetLastMovementInputVector().X, Ch->GetLastMovementInputVector().Y);
			FVector Vel = Ch->GetVelocity();
			FVector Fwd = Ch->GetActorForwardVector();
			GroundSpeed = Vel.Size2D();
			bIsInAir = !Ch->GetCharacterMovement()->IsMovingOnGround();
			// Movement angle relative to facing (compensated by mesh component yaw)
			float VelYaw = FMath::Atan2(Vel.Y, Vel.X);
			float FwdYaw = FMath::Atan2(Fwd.Y, Fwd.X);
			MoveAngleDeg = FMath::RadiansToDegrees(FMath::FindDeltaAngleRadians(FwdYaw, VelYaw));
		}
	}
	// Locomotion clip selection is performed in the native update; the actual
	// bone-space playback uses Server AnimationSequences via UAnimationLibrary
	// from the AnimBlueprint (C++ selects CurrentClip; BP graph plays it).
	// Here we keep CurrentClip coherent with movement when idle.
	if (OverrideState == TEXT("Death") || OverrideState == TEXT("Sleep") || OverrideState == TEXT("Prone") || OverrideState == TEXT("Stun"))
	{
		// Sticky override states are managed by gameplay code (SetOverrideState via Blueprint).
	}
	else if (CurrentClip != TEXT("dialogue") && CurrentClip != TEXT("melee_1") && CurrentClip != TEXT("melee_2") && CurrentClip != TEXT("melee_3")
		&& CurrentClip != TEXT("reload") && CurrentClip != TEXT("channel_loop") && CurrentClip != TEXT("charge_hold"))
	{
		// Only auto-pick locomotion when not in a sustained action; actions are
		// entered explicitly via PlayNamedClip (montage-like C++ calls).
		if (!bIsInAir && GroundSpeed > 30.0f)
		{
			FString Sfx = DirectionSuffix(MoveAngleDeg);
			FString Mode = GroundSpeed > 350.0f ? TEXT("run") : TEXT("walk");
			CurrentClip = Mode + TEXT("_") + Sfx;
			if (GroundSpeed > 600.0f) CurrentClip = TEXT("sprint_f");
		}
		else if (!bIsInAir && GroundSpeed <= 30.0f)
		{
			// Keep idle variant if already idle; otherwise fall back to combat idle
			if (CurrentClip.StartsWith(TEXT("walk")) || CurrentClip.StartsWith(TEXT("run")) || CurrentClip == TEXT("sprint_f"))
			{
				CurrentClip = TEXT("idle_combat");
			}
		}
	}
	PlaybackRate = FMath::Clamp(PlaybackRate, 0.5f, 1.5f);

	// Play the selected clip on the mesh (native playback; AnimBP drives HUD/state).
	{
		UAnimSequence* Seq = FindClip(CurrentClip);
		if (Seq)
		{
			if (APawn* P2 = TryGetPawnOwner())
			{
				if (ACharacter* C2 = Cast<ACharacter>(P2))
				{
					USkeletalMeshComponent* SMC = C2->GetMesh();
					if (SMC)
					{
						bool bLoop = CurrentClip.StartsWith(TEXT("idle")) || CurrentClip.StartsWith(TEXT("walk")) || CurrentClip.StartsWith(TEXT("run")) || CurrentClip == TEXT("sprint_f") || CurrentClip.EndsWith(TEXT("loop")) || CurrentClip == TEXT("jump_air") || CurrentClip == TEXT("knockup_air") || CurrentClip == TEXT("prone_front") || CurrentClip == TEXT("prone_back") || CurrentClip == TEXT("sleep_loop");
						if (SMC->AnimationData.AnimToPlay != reinterpret_cast<UAnimationAsset*>(Seq))
						{
							SMC->PlayAnimation(Seq, bLoop);
						}
						SMC->AnimationData.SavedPlayRate = PlaybackRate;
					}
				}
			}
		}
	}
}

void UMorphRigAnimInstance::EnsureLibrary()
{
	if (ClipLibrary.Num() > 0) return;
	for (const FString& Id : AllClipIds())
	{
		FSoftObjectPath Path(FString::Printf(TEXT("/Game/MorphRig/Animations/%s.%s"), *Id, *Id));
		if (UAnimSequence* Seq = Cast<UAnimSequence>(Path.TryLoad()))
		{
			ClipLibrary.Add(Id, Seq);
		}
	}
}

UAnimSequence* UMorphRigAnimInstance::FindClip(const FString& Id)
{
	if (const TObjectPtr<UAnimSequence>* Found = ClipLibrary.Find(Id))
	{
		return *Found;
	}
	return nullptr;
}
