// MorphRig - character control: camera, states, actions and the showcase.
#include "MorphRigCharacter.h"

#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/LineBatchComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigHUD.h"
#include "MorphRigLog.h"
#include "MorphRigPerfLogger.h"
#include "ReferenceSkeleton.h"
#include "Sound/SoundBase.h"
#include "UnrealClient.h"
#include "HAL/FileManager.h"

UAnimSequenceBase* AMorphRigCharacter::FindClip(const FString& ClipName) const
{
	if (const TObjectPtr<UAnimSequenceBase>* Found = ClipLibrary.Find(ClipName))
	{
		return *Found;
	}
	return nullptr;
}

void AMorphRigCharacter::SetState(EMorphRigState NewState, const FString& ClipName,
								  bool bLoop)
{
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetState(NewState);
		AI->SetActiveClip(ClipName);
		AI->ApplyBaseSequence(FindClip(ClipName), bLoop);
	}
}

FString AMorphRigCharacter::CurrentStateName() const
{
	if (const UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		return StaticEnum<EMorphRigState>()->GetNameStringByValue(
			static_cast<int64>(AI->State));
	}
	return TEXT("None");
}

bool AMorphRigCharacter::PlayClip(const FString& ClipName, float InPlayRate)
{
	UAnimSequenceBase* Sequence = FindClip(ClipName);
	if (!Sequence)
	{
		UE_LOG(LogMorphRig, Warning, TEXT("unknown clip %s"), *ClipName);
		return false;
	}
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->PlayRate = InPlayRate;
		AI->SetActiveClip(ClipName);
		AI->ApplyBaseSequence(Sequence, false);
	}
	ActionClipName = ClipName;
	ActionDuration = Sequence->GetPlayLength() / FMath::Max(InPlayRate, 0.01f);
	ActionTimer = 0.0f;
	ActionWeight = 1.0f;
	return true;
}

bool AMorphRigCharacter::TriggerAction(const FString& ClipName)
{
	UAnimSequenceBase* Sequence = FindClip(ClipName);
	if (!Sequence)
	{
		UE_LOG(LogMorphRig, Warning, TEXT("unknown clip %s"), *ClipName);
		return false;
	}
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetActiveClip(ClipName);
		if (ClipName.StartsWith(TEXT("dash_")))
		{
			// A dash runs on the base layer so the pose is the dash itself and
			// the root motion of the clip drives the capsule.
			AI->ApplyBaseSequence(Sequence, false);
		}
		else
		{
			AI->ApplyActionSequence(Sequence);
		}
	}
	ActiveActionClip = ClipName;
	ActionDuration = Sequence->GetPlayLength();
	ActionTimer = 0.0f;
	ActionWeight = 0.0f;

	// The dash clips carry root motion.  Unreal 5.8 removed the dedicated
	// root motion movement mode: while the animation produces root motion the
	// movement component keeps the root motion velocity instead of recomputing
	// it from the input, so the capsule is driven by the clip.
	if (ClipName.StartsWith(TEXT("dash_")))
	{
		DashStartLocation = GetActorLocation();
		if (UCharacterMovementComponent* Move = GetCharacterMovement())
		{
			Move->MovementMode = EMovementMode::MOVE_Walking;
			// The dash covers two metres in a third of a second, which is
			// faster than the walk speed.  Without raising the limit the
			// movement component would clamp the root motion velocity and the
			// capsule would only travel a part of the clip.
			Move->MaxWalkSpeed = DashSpeed;
		}
		if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
		{
			AI->SetState(EMorphRigState::Dash);
		}
	}
	UE_LOG(LogMorphRig, Log, TEXT("action %s"), *ClipName);
	return true;
}

void AMorphRigCharacter::ResetCharacter()
{
	bAiming = false;
	ActionWeight = 0.0f;
	AimWeight = 0.0f;
	ActiveActionClip.Empty();
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->MovementMode = EMovementMode::MOVE_Walking;
	}
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->bAiming = false;
		AI->SetState(EMorphRigState::Idle);
		AI->SetActiveClip(TEXT("idle_combat"));
		AI->ApplyBaseSequence(FindClip(TEXT("idle_combat")), true);
		AI->ApplyActionWeight(0.0f);
		AI->ApplyAimWeight(0.0f);
	}
	Trace.Add(TEXT("state=Reset"));
	UE_LOG(LogMorphRig, Log, TEXT("reset"));
}

void AMorphRigCharacter::BlinkTo(const FVector& Destination)
{
	PendingBlinkTarget = Destination;
	bPendingBlink = true;
	TriggerAction(TEXT("blink_out"));
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetState(EMorphRigState::Blink);
	}
	Trace.Add(FString::Printf(TEXT("event=blink_out dest=%s"),
							  *Destination.ToCompactString()));
}

void AMorphRigCharacter::ApplyHit(FVector FromWorldDirection)
{
	const FVector Dir = FromWorldDirection.GetSafeNormal2D();
	float Yaw = 90.0f;
	if (!Dir.IsNearlyZero())
	{
		Yaw = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
	}
	FString Clip = TEXT("hit_f");
	if (Yaw > 45.0f && Yaw <= 135.0f) { Clip = TEXT("hit_r"); }
	else if (Yaw < -45.0f && Yaw >= -135.0f) { Clip = TEXT("hit_l"); }
	else if (Yaw <= -135.0f || Yaw > 135.0f) { Clip = TEXT("hit_b"); }
	TriggerAction(Clip);
	Trace.Add(FString::Printf(TEXT("event=hit clip=%s yaw=%.1f"), *Clip, Yaw));
}

void AMorphRigCharacter::SetTeam(int32 InTeam)
{
	TeamIndex = FMath::Clamp(InTeam, 0, 1);
	const FLinearColor Amber(1.0f, 0.45f, 0.06f, 1.0f);
	const FLinearColor Cyan(0.05f, 0.70f, 1.0f, 1.0f);
	const FLinearColor Color = (TeamIndex == 0) ? Amber : Cyan;
	if (AccentMID)
	{
		AccentMID->SetVectorParameterValue(TEXT("TeamColor"), Color);
	}
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetTeamColor(Color);
	}
	Trace.Add(FString::Printf(TEXT("event=team index=%d"), TeamIndex));
}

void AMorphRigCharacter::SetLOD(int32 InLOD)
{
	LODIndex = FMath::Clamp(InLOD, 0, 2);
	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		Mesh->SetPredictedLODLevel(LODIndex);
	}
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->LODIndex = LODIndex;
	}
	Trace.Add(FString::Printf(TEXT("event=lod index=%d"), LODIndex));
}

void AMorphRigCharacter::SetShowSkeleton(bool bInShow)
{
	bShowSkeletonOverlay = bInShow;
	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		Mesh->SetRenderCustomDepth(bInShow);
		Mesh->SetCustomDepthStencilValue(bInShow ? 1 : 0);
	}
	Trace.Add(FString::Printf(TEXT("event=skeleton %s"),
							  bInShow ? TEXT("on") : TEXT("off")));
}

void AMorphRigCharacter::SetMaterialView(EMorphRigMaterialView InView)
{
	MaterialView = InView;

	USkeletalMeshComponent* Mesh = GetMesh();
	if (!Mesh)
	{
		return;
	}

	// Remember the authored materials the first time the view is changed, so
	// the textured view can be restored exactly, including the accent
	// instance that carries the team colour.
	if (AuthoredMaterials.Num() == 0)
	{
		for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
		{
			AuthoredMaterials.Add(Mesh->GetMaterial(Index));
		}
	}

	UMaterialInterface* Override = nullptr;
	switch (InView)
	{
	case EMorphRigMaterialView::Normal:
		Override = NormalViewMaterial;
		break;
	case EMorphRigMaterialView::Clay:
		Override = ClayViewMaterial;
		break;
	case EMorphRigMaterialView::Textured:
	default:
		Override = nullptr;
		break;
	}

	if (Override == nullptr && InView != EMorphRigMaterialView::Textured)
	{
		// The helper material is missing, keep the authored one.
		UE_LOG(LogMorphRig, Warning,
			   TEXT("the material view %d is not available"), static_cast<int32>(InView));
		return;
	}

	for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
	{
		if (Override)
		{
			Mesh->SetMaterial(Index, Override);
		}
		else if (AuthoredMaterials.IsValidIndex(Index))
		{
			Mesh->SetMaterial(Index, AuthoredMaterials[Index]);
		}
	}

	Trace.Add(FString::Printf(TEXT("event=materialview view=%s"),
							  *GetMaterialViewName()));

	// The copies in the room follow the player.
	for (AMorphRigCharacter* Extra : ExtraInstances)
	{
		if (Extra && Extra != this)
		{
			Extra->SetMaterialView(InView);
		}
	}
}

FString AMorphRigCharacter::GetMaterialViewName() const
{
	switch (MaterialView)
	{
	case EMorphRigMaterialView::Normal:
		return TEXT("normal");
	case EMorphRigMaterialView::Clay:
		return TEXT("clay");
	case EMorphRigMaterialView::Textured:
	default:
		return TEXT("textured");
	}
}

void AMorphRigCharacter::ToggleMaterialView()
{
	const uint8 Next = (static_cast<uint8>(MaterialView) + 1) % 3;
	SetMaterialView(static_cast<EMorphRigMaterialView>(Next));
}

void AMorphRigCharacter::SetCameraMode(EMorphRigCameraMode InMode)
{
	CameraMode = InMode;
	UpdateCamera();
	Trace.Add(FString::Printf(TEXT("event=camera mode=%d"), static_cast<int32>(InMode)));
	// The framing is logged with the positions, so a capture can be checked
	// against the numbers without opening the level in the editor.
	UE_LOG(LogMorphRig, Log, TEXT("camera mode=%d at %s look %s"),
		   static_cast<int32>(InMode),
		   Camera ? *Camera->GetComponentLocation().ToCompactString() : TEXT("none"),
		   Camera ? *Camera->GetForwardVector().ToCompactString() : TEXT("none"));
}

void AMorphRigCharacter::UpdateCamera()
{
	if (!Camera)
	{
		return;
	}

	// The showcase framings are built in the Operative's own frame: it faces
	// +X in Unreal and its right hand points to +Y.  The actor origin sits in
	// the middle of the capsule, 88 cm above the floor, so the head is at
	// +80 in that frame.
	const FVector Base = GetActorLocation();
	const FRotationMatrix Facing(GetActorRotation());

	FVector Offset = FVector(-70.0f, 45.0f, 22.0f);
	FVector Target = FVector(0.0f, 0.0f, 66.0f);
	float FieldOfView = 55.0f;

	switch (CameraMode)
	{
	case EMorphRigCameraMode::Close:
		// over the right shoulder, the head and the upper body fill the frame
		Offset = FVector(-62.0f, 42.0f, 16.0f);
		Target = FVector(0.0f, 0.0f, 72.0f);
		FieldOfView = 55.0f;
		break;
	case EMorphRigCameraMode::FullBodySide:
		// the whole body from the right, 420 cm away.  Unreal's field of view
		// is horizontal, so at 16:9 the vertical field is 0.56 of it and the
		// 180 cm of the Operative need that distance.
		Offset = FVector(0.0f, 420.0f, 2.0f);
		Target = FVector(0.0f, 0.0f, 2.0f);
		FieldOfView = 45.0f;
		break;
	case EMorphRigCameraMode::FullBodyFront:
		// the whole body from the front
		Offset = FVector(420.0f, 0.0f, 2.0f);
		Target = FVector(0.0f, 0.0f, 2.0f);
		FieldOfView = 45.0f;
		break;
	case EMorphRigCameraMode::TopDown:
		Offset = FVector(0.0f, -40.0f, 420.0f);
		Target = FVector(0.0f, 0.0f, 0.0f);
		FieldOfView = 60.0f;
		break;
	case EMorphRigCameraMode::Face:
		// close on the face, 75 cm in front of the head
		Offset = FVector(75.0f, 0.0f, 80.0f);
		Target = FVector(0.0f, 0.0f, 80.0f);
		FieldOfView = 35.0f;
		break;
	}

	Camera->FieldOfView = FieldOfView;

	const FVector Location = Base + Facing.TransformVector(Offset);
	const FVector LookAt = Base + Facing.TransformVector(Target);
	Camera->SetWorldLocation(Location);
	const FVector Dir = (LookAt - Location).GetSafeNormal();
	Camera->SetWorldRotation(Dir.Rotation());
}

FString AMorphRigCharacter::PickLocomotionClip() const
{
	const FVector Velocity = GetVelocity();
	const float Speed = Velocity.Size2D();
	if (Speed < 12.0f)
	{
		return TEXT("idle_combat");
	}
	const FRotator YawRotation(0.0f, GetActorRotation().Yaw, 0.0f);
	const FVector Local = FRotationMatrix(YawRotation).InverseTransformVector(
		Velocity.GetSafeNormal2D());
	// Unreal characters face +X and their right hand points to +Y
	const float Forward = Local.X;
	const float Right = Local.Y;

	const bool bRun = Speed > 300.0f;
	const FString Prefix = bRun ? TEXT("run") : TEXT("walk");
	FString Direction;
	if (Forward > 0.55f) { Direction = TEXT("_f"); }
	else if (Forward < -0.55f) { Direction = TEXT("_b"); }
	else if (Right > 0.55f) { Direction = TEXT("_r"); }
	else if (Right < -0.55f) { Direction = TEXT("_l"); }
	else if (Forward > 0.0f && Right > 0.0f) { Direction = TEXT("_fr"); }
	else if (Forward > 0.0f && Right < 0.0f) { Direction = TEXT("_fl"); }
	else if (Forward < 0.0f && Right > 0.0f) { Direction = TEXT("_br"); }
	else { Direction = TEXT("_bl"); }
	return Prefix + Direction;
}

void AMorphRigCharacter::Tick(float DeltaSeconds)
{
	const double Start = FPlatformTime::Seconds();

	Super::Tick(DeltaSeconds);

	UpdateCamera();
	UpdateSkeletonOverlay();
	UpdateGroundAdaptation();

	UMorphRigAnimInstance* AI = GetMorphAnimInstance();
	if (!AI)
	{
		FMorphRigFrameBreakdown::Current().Character =
			(FPlatformTime::Seconds() - Start) * 1000.0;
		return;
	}

	const FVector Velocity = GetVelocity();
	AI->MoveSpeed = Velocity.Size2D();
	const FRotator YawRotation(0.0f, GetActorRotation().Yaw, 0.0f);
	const FVector Local = FRotationMatrix(YawRotation).InverseTransformVector(
		Velocity.GetSafeNormal2D());
	// +X is the right component, +Y the forward component
	AI->MoveDirection = FVector2D(Local.Y, Local.X);

	if (APlayerController* PC = Cast<APlayerController>(Controller))
	{
		const FRotator Control = PC->GetControlRotation();
		AI->AimYaw = FMath::UnwindDegrees(Control.Yaw - GetActorRotation().Yaw);
		AI->AimPitch = -Control.Pitch;
	}

	// base state clip
	if (AI->State == EMorphRigState::Performance)
	{
		// the spoken performance owns the base layer until it has finished
		if (AI->GetBaseTime() >= AI->GetBaseLength() - 0.05f)
		{
			AI->SetState(EMorphRigState::Idle);
			AI->RaiseEvent(TEXT("performance_end"));
			Trace.Add(TEXT("event=performance_end"));
		}
	}
	else if (ActiveActionClip.IsEmpty() || ActionWeight <= 0.01f)
	{
		const FString Wanted = PickLocomotionClip();
		if (AI->ActiveClip != Wanted && AI->State != EMorphRigState::Dash &&
			AI->State != EMorphRigState::Death)
		{
			AI->SetActiveClip(Wanted);
			AI->ApplyBaseSequence(FindClip(Wanted), true);
		}
	}

	// action layer weight: ramp in over 0.12 s, out over the last 0.25 s
	if (!ActiveActionClip.IsEmpty())
	{
		ActionTimer += DeltaSeconds;
		const float FadeIn = FMath::Clamp(ActionTimer / 0.12f, 0.0f, 1.0f);
		const float FadeOut = FMath::Clamp((ActionDuration - ActionTimer) / 0.25f,
										   0.0f, 1.0f);
		ActionWeight = FMath::Min(FadeIn, FadeOut);
		if (ActionTimer >= ActionDuration)
		{
			ActionWeight = 0.0f;
			if (ActiveActionClip.StartsWith(TEXT("dash_")))
			{
				// The dash is the only clip with root motion: it drives the
				// capsule and has to cover two metres.
				const float Distance = FVector::Dist(DashStartLocation, GetActorLocation());
				Trace.Add(FString::Printf(TEXT("event=dash clip=%s distance=%.1fcm"),
										  *ActiveActionClip, Distance));
				UE_LOG(LogMorphRig, Log, TEXT("dash %s travelled %.1f cm"),
					   *ActiveActionClip, Distance);
			}
			ActiveActionClip.Empty();
			if (UCharacterMovementComponent* Move = GetCharacterMovement())
			{
				Move->MovementMode = EMovementMode::MOVE_Walking;
				Move->MaxWalkSpeed = WalkSpeed;
			}
			if (AI->State == EMorphRigState::Dash)
			{
				AI->SetState(EMorphRigState::Idle);
			}
		}
	}
	AI->ApplyActionWeight(ActionWeight);

	// aim layer
	AimWeight = bAiming ? 1.0f : 0.0f;
	AI->ApplyAimWeight(AimWeight);
	if (bAiming)
	{
		const int32 YawIndex = AI->AimYaw < -20.0f ? 0 : (AI->AimYaw > 20.0f ? 2 : 1);
		const int32 PitchIndex = AI->AimPitch > 15.0f ? 0
								   : (AI->AimPitch < -15.0f ? 2 : 1);
		static const TCHAR* PitchNames[3] = {TEXT("down"), TEXT("level"), TEXT("up")};
		static const TCHAR* YawNames[3] = {TEXT("left"), TEXT("center"), TEXT("right")};
		const FString AimClip = FString::Printf(TEXT("aim_%s_%s"),
												PitchNames[PitchIndex], YawNames[YawIndex]);
		if (AI->ActiveClip != AimClip)
		{
			AI->ApplyAimSequence(FindClip(AimClip));
		}
	}

	// blink teleport
	if (bPendingBlink && ActionTimer > 0.22f)
	{
		bPendingBlink = false;
		SetActorLocation(PendingBlinkTarget, false, nullptr, ETeleportType::TeleportPhysics);
		TriggerAction(TEXT("blink_in"));
	}

	if (bShowcaseRunning)
	{
		TickShowcase(DeltaSeconds);
	}

	// The camera tour: every few seconds the framing moves on.
	if (CameraCycleSeconds > 0.0f)
	{
		CameraCycleTimer += DeltaSeconds;
		if (CameraCycleTimer >= CameraCycleSeconds)
		{
			CameraCycleTimer = 0.0f;
			const uint8 Next = (static_cast<uint8>(CameraMode) + 1) % 5;
			SetCameraMode(static_cast<EMorphRigCameraMode>(Next));
			if (!ShotDirectory.IsEmpty())
			{
				TakeScreenshot(FString::Printf(TEXT("mode%d"), static_cast<int32>(Next)));
			}
		}
	}

	// The scripted screenshot, so the showcase can be captured without a
	// human at the keyboard.
	if (!ShotDirectory.IsEmpty() && !bShotTaken)
	{
		GameTime += DeltaSeconds;
		if (GameTime >= ShotDelay)
		{
			bShotTaken = true;
			TakeScreenshot(FString::Printf(TEXT("mode%d"), static_cast<int32>(CameraMode)));
		}
	}

	FMorphRigFrameBreakdown::Current().Character =
		(FPlatformTime::Seconds() - Start) * 1000.0;
}

// ---------------------------------------------------------------------------
// deterministic showcase sequence
// ---------------------------------------------------------------------------

namespace
{
struct FShowcaseStep
{
	const TCHAR* State;
	const TCHAR* Clip;
	float Duration;
	bool bAim;
};
}

static const FShowcaseStep GShowcaseSteps[] = {
	{TEXT("Idle"), TEXT("idle_combat"), 2.0f, false},
	{TEXT("Locomotion"), TEXT("walk_f"), 2.5f, false},
	{TEXT("Locomotion"), TEXT("run_f"), 2.0f, false},
	{TEXT("Aim"), TEXT("aim_level_center"), 1.5f, true},
	{TEXT("Aim"), TEXT("aim_up_left"), 1.5f, true},
	{TEXT("Attack"), TEXT("melee_1"), 1.2f, false},
	{TEXT("Attack"), TEXT("ranged_fire"), 0.8f, false},
	{TEXT("Cast"), TEXT("cast_directional"), 1.2f, false},
	{TEXT("Charge"), TEXT("charge_start"), 1.0f, false},
	{TEXT("Channel"), TEXT("channel_start"), 0.8f, false},
	{TEXT("Channel"), TEXT("channel_loop"), 2.0f, false},
	{TEXT("Hit"), TEXT("hit_f"), 0.8f, false},
	{TEXT("Dash"), TEXT("dash_f"), 0.8f, false},
	{TEXT("Blink"), TEXT("blink_out"), 0.6f, false},
	{TEXT("Death"), TEXT("death_front"), 2.5f, false},
	{TEXT("Respawn"), TEXT("respawn"), 2.0f, false},
};

void AMorphRigCharacter::StartShowcaseSequence()
{
	Trace.Reset();
	ShowcaseStep = 0;
	ShowcaseTimer = 0.0f;
	bShowcaseRunning = true;
	const FString Line = FString::Printf(TEXT("showcase start steps=%d"),
										  UE_ARRAY_COUNT(GShowcaseSteps));
	Trace.Add(Line);
	UE_LOG(LogMorphRig, Log, TEXT("%s"), *Line);
}

void AMorphRigCharacter::StopShowcaseSequence()
{
	bShowcaseRunning = false;
	Trace.Add(TEXT("showcase stop"));
}

void AMorphRigCharacter::PlayPerformance()
{
	// The spoken performance is a 12.5 s clip with the face acting baked in
	// as morph target curves, so it runs on the base layer.
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetState(EMorphRigState::Performance);
		AI->SetActiveClip(TEXT("dialogue"));
		AI->ApplyBaseSequence(FindClip(TEXT("dialogue")), false);
		AI->RaiseEvent(TEXT("performance_start"));
	}

	if (USoundBase* Speech = LoadObject<USoundBase>(nullptr, TEXT("/Game/MorphRig/Audio/S_Dialogue")))
	{
		UGameplayStatics::PlaySound2D(this, Speech);
	}

	Trace.Add(TEXT("event=performance clip=dialogue"));
	UE_LOG(LogMorphRig, Log, TEXT("performance started"));
}

void AMorphRigCharacter::ToggleAnimationBrowser()
{
	bBrowserOpen = !bBrowserOpen;
	if (APlayerController* PC = Cast<APlayerController>(Controller))
	{
		if (AMorphRigHUD* Hud = Cast<AMorphRigHUD>(PC->GetHUD()))
		{
			Hud->SetBrowserVisible(bBrowserOpen);
			Hud->SetBrowserFilter(BrowserFilter);
		}
	}
	Trace.Add(FString::Printf(TEXT("event=browser %s"),
							  bBrowserOpen ? TEXT("open") : TEXT("closed")));
}

void AMorphRigCharacter::AppendToBrowserFilter(const FString& Characters)
{
	if (!bBrowserOpen)
	{
		return;
	}
	BrowserFilter += Characters;
	if (APlayerController* PC = Cast<APlayerController>(Controller))
	{
		if (AMorphRigHUD* Hud = Cast<AMorphRigHUD>(PC->GetHUD()))
		{
			Hud->SetBrowserFilter(BrowserFilter);
		}
	}
}

void AMorphRigCharacter::AppendFilterKey(FKey Key)
{
	// Only plain letters reach the filter, everything else is ignored.
	const FString Name = Key.GetFName().ToString();
	if (Name.Len() != 1 || !FChar::IsAlpha(Name[0]))
	{
		return;
	}
	BrowserSelection = 0;
	AppendToBrowserFilter(Name.ToUpper());
}

void AMorphRigCharacter::MoveBrowserSelection(int32 Delta)
{
	if (!bBrowserOpen)
	{
		return;
	}
	const TArray<FString> Results = SearchClips(BrowserFilter);
	if (Results.Num() == 0)
	{
		BrowserSelection = 0;
		return;
	}
	BrowserSelection = FMath::Clamp(BrowserSelection + Delta, 0, Results.Num() - 1);
}

void AMorphRigCharacter::PlaySelectedClip()
{
	if (!bBrowserOpen)
	{
		return;
	}
	const TArray<FString> Results = SearchClips(BrowserFilter);
	if (Results.Num() == 0)
	{
		return;
	}
	BrowserSelection = FMath::Clamp(BrowserSelection, 0, Results.Num() - 1);
	const FString Clip = Results[BrowserSelection];

	// The clip plays on the base layer so that every delivered clip can be
	// inspected on its own, whatever its layer or form.
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetActiveClip(Clip);
		AI->ApplyBaseSequence(FindClip(Clip), false);
		AI->RaiseEvent(FString::Printf(TEXT("browser_play %s"), *Clip));
	}
	ActiveActionClip.Empty();
	ActionWeight = 0.0f;

	Trace.Add(FString::Printf(TEXT("event=browser_play clip=%s"), *Clip));
	UE_LOG(LogMorphRig, Log, TEXT("browser play %s"), *Clip);
}

void AMorphRigCharacter::MoveBrowserSelectionUp()
{
	MoveBrowserSelection(-1);
}

void AMorphRigCharacter::MoveBrowserSelectionDown()
{
	MoveBrowserSelection(1);
}

void AMorphRigCharacter::SlowerPlayback()
{
	StepPlayRate(-0.1f);
}

void AMorphRigCharacter::FasterPlayback()
{
	StepPlayRate(0.1f);
}

void AMorphRigCharacter::StepPlayRate(float Delta){
	PlayRate = FMath::Clamp(PlayRate + Delta, 0.5f, 1.5f);
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->PlayRate = PlayRate;
	}
	Trace.Add(FString::Printf(TEXT("event=playrate %.2f"), PlayRate));
	UE_LOG(LogMorphRig, Log, TEXT("play rate %.2f"), PlayRate);
}

void AMorphRigCharacter::UpdateGroundAdaptation()
{
	// Keep the feet on the floor of the room: a line trace finds the ground
	// under the character and the mesh follows it with a smoothed offset, so
	// the ramp and the steps do not leave the pelvis floating.
	if (!GetWorld())
	{
		return;
	}
	const FVector Base = GetActorLocation();
	FHitResult Hit;
	const FVector Start = Base + FVector(0.0f, 0.0f, 120.0f);
	const FVector End = Base - FVector(0.0f, 0.0f, 200.0f);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphRigGround), false, this);
	if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldStatic,
											Params))
	{
		const float Target = Hit.ImpactPoint.Z - Base.Z;
		GroundOffset = FMath::FInterpTo(GroundOffset, Target, 0.016f, 12.0f);
	}
	else
	{
		GroundOffset = FMath::FInterpTo(GroundOffset, 0.0f, 0.016f, 8.0f);
	}

	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		Mesh->SetRelativeLocation(FVector(0.0f, 0.0f, GroundOffset));
	}
}

void AMorphRigCharacter::BackspaceBrowserFilter()
{
	if (!bBrowserOpen || BrowserFilter.IsEmpty())
	{
		return;
	}
	BrowserFilter.LeftChopInline(1, EAllowShrinking::No);
	if (APlayerController* PC = Cast<APlayerController>(Controller))
	{
		if (AMorphRigHUD* Hud = Cast<AMorphRigHUD>(PC->GetHUD()))
		{
			Hud->SetBrowserFilter(BrowserFilter);
		}
	}
}

void AMorphRigCharacter::ApplyCommandLineOptions()
{
	// Only the player Operative reads the command line.  A copy would read
	// it as well and spawn nine copies of its own, over and over.
	if (bIsShowcaseInstance)
	{
		return;
	}

	// -MorphRigInstances=N spawns the extra Operatives at start up, so the
	// one versus ten comparison can be run without a human at the keyboard.
	int32 Instances = 1;
	if (FParse::Value(FCommandLine::Get(), TEXT("MorphRigInstances="), Instances))
	{
		Instances = FMath::Clamp(Instances, 1, 10);
	}
	if (Instances > 1)
	{
		ToggleInstanceCount();
		UE_LOG(LogMorphRig, Log, TEXT("command line requested %d instances"), Instances);
	}

	// -MorphRigShowcase starts the deterministic sequence right away.
	if (FParse::Param(FCommandLine::Get(), TEXT("MorphRigShowcase")))
	{
		StartShowcaseSequence();
	}

	// -MorphRigCamera=MODE picks the framing at start up, so a capture can be
	// taken without a human at the keyboard.  The same five framings are
	// reachable in game with the Tab key.
	FString CameraName;
	if (FParse::Value(FCommandLine::Get(), TEXT("MorphRigCamera="), CameraName))
	{
		CameraName.TrimStartAndEndInline();
		CameraName.ToLowerInline();
		bool bKnown = true;
		if (CameraName == TEXT("close")) { SetCameraMode(EMorphRigCameraMode::Close); }
		else if (CameraName == TEXT("side") || CameraName == TEXT("fullbodyside"))
		{
			SetCameraMode(EMorphRigCameraMode::FullBodySide);
		}
		else if (CameraName == TEXT("front") || CameraName == TEXT("fullbodyfront"))
		{
			SetCameraMode(EMorphRigCameraMode::FullBodyFront);
		}
		else if (CameraName == TEXT("topdown") || CameraName == TEXT("top"))
		{
			SetCameraMode(EMorphRigCameraMode::TopDown);
		}
		else if (CameraName == TEXT("face")) { SetCameraMode(EMorphRigCameraMode::Face); }
		else { bKnown = false; }

		if (bKnown)
		{
			UE_LOG(LogMorphRig, Log, TEXT("command line requested camera %s"), *CameraName);
		}
		else
		{
			UE_LOG(LogMorphRig, Warning, TEXT("unknown camera mode %s"), *CameraName);
		}
	}

	// -MorphRigCameraCycle=SECONDS walks through the five framings on its
	// own, so a capture of every view needs one run of the client.
	float Cycle = 0.0f;
	if (FParse::Value(FCommandLine::Get(), TEXT("MorphRigCameraCycle="), Cycle))
	{
		CameraCycleSeconds = FMath::Max(Cycle, 0.0f);
		CameraCycleTimer = 0.0f;
		UE_LOG(LogMorphRig, Log, TEXT("command line camera cycle every %.1f s"),
			   CameraCycleSeconds);
	}

	// -MorphRigShot=DIR writes a screenshot of the game viewport into the
	// directory, the showcase can be captured without an X server.
	FParse::Value(FCommandLine::Get(), TEXT("MorphRigShot="), ShotDirectory);
	if (!ShotDirectory.IsEmpty())
	{
		float Delay = 6.0f;
		FParse::Value(FCommandLine::Get(), TEXT("MorphRigShotDelay="), Delay);
		ShotDelay = FMath::Max(Delay, 0.5f);
		UE_LOG(LogMorphRig, Log, TEXT("command line screenshots into %s after %.1f s"),
			   *ShotDirectory, ShotDelay);
	}

	// -MorphRigMaterialView=VIEW picks the shading at start up.  The view is
	// applied once the mesh is in place, the material slots are needed.
	FParse::Value(FCommandLine::Get(), TEXT("MorphRigMaterialView="), PendingMaterialView);
	if (!PendingMaterialView.IsEmpty())
	{
		PendingMaterialView.ToLowerInline();
		UE_LOG(LogMorphRig, Log, TEXT("command line material view %s"),
			   *PendingMaterialView);
	}
}

void AMorphRigCharacter::TakeScreenshot(const FString& Suffix)
{
	if (ShotDirectory.IsEmpty())
	{
		return;
	}
	IFileManager::Get().MakeDirectory(*ShotDirectory, true);
	const FString File = FString::Printf(TEXT("%s/MorphRig_%s.png"),
										  *ShotDirectory, *Suffix);
	FScreenshotRequest::RequestScreenshot(File, /*bInShowUI*/ true,
										  /*bAddFilenameSuffix*/ false,
										  /*bHdrScreenshot*/ false,
										  FIntRect(),
										  /*bInRestrictToGameViewport*/ true);
	UE_LOG(LogMorphRig, Log, TEXT("screenshot %s"), *File);
}

void AMorphRigCharacter::ToggleInstanceCount()
{
	// one Operative or ten: the extra copies stand in a grid next to the player
	if (ExtraInstances.Num() > 0)
	{
		for (AMorphRigCharacter* Extra : ExtraInstances)
		{
			if (Extra)
			{
				Extra->Destroy();
			}
		}
		ExtraInstances.Reset();
		Trace.Add(TEXT("event=instances count=1"));
		UE_LOG(LogMorphRig, Log, TEXT("instances 1"));
		return;
	}
	if (!GetWorld())
	{
		return;
	}

	const FVector Base = GetActorLocation();
	for (int32 Index = 0; Index < 9; ++Index)
	{
		const int32 Column = Index % 3 - 1;
		const int32 Row = Index / 3 - 1;
		const FVector Offset(Column * 190.0f, Row * 190.0f - 190.0f, 0.0f);
		const FVector Location = Base + Offset;

		// The spawn is deferred so the copy is marked before its BeginPlay
		// runs.  Otherwise the copy would read the command line again and
		// spawn nine more copies of its own.
		const FTransform SpawnTransform(FRotator::ZeroRotator, Location);
		AMorphRigCharacter* Extra = GetWorld()->SpawnActorDeferred<AMorphRigCharacter>(
			GetClass(), SpawnTransform, this, nullptr,
			ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
		if (Extra)
		{
			Extra->bIsShowcaseInstance = true;
			Extra->FinishSpawning(SpawnTransform);
			ExtraInstances.Add(Extra);
		}
	}

	Trace.Add(FString::Printf(TEXT("event=instances count=%d"), GetInstanceCount()));
	UE_LOG(LogMorphRig, Log, TEXT("instances %d"), GetInstanceCount());
}

void AMorphRigCharacter::UpdateSkeletonOverlay()
{
	if (!SkeletonLines)
	{
		return;
	}
	SkeletonLines->Flush();

	if (!bShowSkeletonOverlay)
	{
		SkeletonLines->SetVisibility(false);
		return;
	}

	USkeletalMeshComponent* Mesh = GetMesh();
	if (!Mesh || !Mesh->GetSkeletalMeshAsset())
	{
		return;
	}

	SkeletonLines->SetVisibility(true);
	const FReferenceSkeleton& RefSkeleton = Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
	const FLinearColor BoneColor(0.35f, 0.85f, 1.0f, 1.0f);
	const FLinearColor RootColor(1.0f, 0.55f, 0.12f, 1.0f);

	for (int32 BoneIndex = 0; BoneIndex < RefSkeleton.GetNum(); ++BoneIndex)
	{
		const int32 ParentIndex = RefSkeleton.GetParentIndex(BoneIndex);
		if (ParentIndex == INDEX_NONE)
		{
			continue;
		}
		const int32 ChildMeshIndex = Mesh->GetBoneIndex(RefSkeleton.GetBoneName(BoneIndex));
		const int32 ParentMeshIndex = Mesh->GetBoneIndex(RefSkeleton.GetBoneName(ParentIndex));
		if (ChildMeshIndex == INDEX_NONE || ParentMeshIndex == INDEX_NONE)
		{
			continue;
		}
		const FVector Start = Mesh->GetBoneTransform(ChildMeshIndex).GetLocation();
		const FVector End = Mesh->GetBoneTransform(ParentMeshIndex).GetLocation();
		const FLinearColor& Color = (ParentIndex == 0) ? RootColor : BoneColor;
		SkeletonLines->DrawLine(Start, End, Color, 0, 1.6f, 0.0f);
	}
}

void AMorphRigCharacter::TickShowcase(float DeltaSeconds)
{
	ShowcaseTimer += DeltaSeconds;
	const FShowcaseStep& Step = GShowcaseSteps[ShowcaseStep];
	if (ShowcaseTimer >= Step.Duration)
	{
		ShowcaseTimer = 0.0f;
		ShowcaseStep = (ShowcaseStep + 1) % UE_ARRAY_COUNT(GShowcaseSteps);
		const FString Line = FString::Printf(TEXT("showcase step=%d state=%s clip=%s"),
											  ShowcaseStep, Step.State, Step.Clip);
		Trace.Add(Line);
		UE_LOG(LogMorphRig, Log, TEXT("%s"), *Line);

		bAiming = Step.bAim;
		if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
		{
			AI->bAiming = Step.bAim;
		}
		if (Step.bAim)
		{
			PlayClip(Step.Clip);
		}
		else
		{
			TriggerAction(Step.Clip);
		}
	}
}
