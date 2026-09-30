#include "MorphPlayerController.h"

#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "MorphOperative.h"
#include "MorphShowcaseGameMode.h"

AMorphPlayerController::AMorphPlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	PrimaryActorTick.bTickEvenWhenPaused = true;
}

void AMorphPlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameOnly Mode;
	Mode.SetConsumeCaptureMouseDown(false);
	SetInputMode(Mode);
	SetShowMouseCursor(true);
}

AMorphOperative* AMorphPlayerController::Op() const
{
	return Cast<AMorphOperative>(GetPawn());
}

AMorphShowcaseGameMode* AMorphPlayerController::GM() const
{
	return GetWorld() ? GetWorld()->GetAuthGameMode<AMorphShowcaseGameMode>() : nullptr;
}

void AMorphPlayerController::SetUIFocus(bool bUI)
{
	bUIFocus = bUI;
	if (bUI)
	{
		FInputModeGameAndUI Mode;
		Mode.SetHideCursorDuringCapture(false);
		SetInputMode(Mode);
	}
	else
	{
		FInputModeGameOnly Mode;
		Mode.SetConsumeCaptureMouseDown(false);
		SetInputMode(Mode);
	}
	SetShowMouseCursor(true);
}

FString AMorphPlayerController::CameraName() const
{
	switch (CamMode)
	{
	case EMorphCamera::ThirdPerson: return TEXT("third-person");
	case EMorphCamera::TopDown: return TEXT("top-down 55deg");
	case EMorphCamera::Side: return TEXT("side");
	case EMorphCamera::Front: return TEXT("front");
	case EMorphCamera::Face: return TEXT("face close-up");
	case EMorphCamera::Free: return TEXT("orbit");
	}
	return TEXT("?");
}

void AMorphPlayerController::SetCamMode(EMorphCamera M)
{
	CamMode = M;
	ArmScale = 1.f;
	OrbitYaw = 0.f;
}

void AMorphPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	if (!Op())
	{
		return;
	}
	HandleKeys(DeltaTime);
	UpdateCamera(DeltaTime);
	if (bSkeleton)
	{
		DrawSkeleton();
	}
}

void AMorphPlayerController::HandleKeys(float Dt)
{
	AMorphOperative* O = Op();
	AMorphShowcaseGameMode* G = GM();
	const bool bShift = Down(EKeys::LeftShift) || Down(EKeys::RightShift);
	if (bCapture)
	{
		return;
	}
	// ---------------------------------------------------------------- UI / presentation (always active)
	if (Pressed(EKeys::F1)) bHelp = !bHelp;
	if (Pressed(EKeys::F2)) SetCamMode(EMorphCamera((uint8(CamMode) + 1) % 6));
	if (Pressed(EKeys::F3) && G) G->ToggleFacePanel();
	if (Pressed(EKeys::F4) && G) G->ToggleBrowser();
	if (Pressed(EKeys::F5)) O->SetTeam(1 - O->GetTeam());
	if (Pressed(EKeys::F6)) O->SetForcedLOD((O->GetForcedLOD() + 1) % 4);
	if (Pressed(EKeys::F7) && G) G->SetInstanceCount(G->GetInstanceCount() > 1 ? 1 : 10);
	if (Pressed(EKeys::F8)) O->SetOutline(!O->GetOutline());
	if (Pressed(EKeys::F9) && G) G->StartSequence(false);
	if (Pressed(EKeys::F10)) O->SetStance(EMorphStance((int32(O->GetStance()) + 1) % 3));
	if (Pressed(EKeys::F11)) O->SetStrafe(!O->IsStrafe());
	if (Pressed(EKeys::O)) bSkeleton = !bSkeleton;
	if (bUIFocus || bScripted)
	{
		if (bScripted && Pressed(EKeys::Escape) && G)
		{
			G->StopSequence();
		}
		return;   // text entry / scripted playback own the character
	}
	// ---------------------------------------------------------------- locomotion
	FVector2D In(0.f, 0.f);
	if (Down(EKeys::W)) In.X += 1.f;
	if (Down(EKeys::S)) In.X -= 1.f;
	if (Down(EKeys::D)) In.Y += 1.f;
	if (Down(EKeys::A)) In.Y -= 1.f;
	if (Pressed(EKeys::CapsLock) || Pressed(EKeys::LeftControl)) bWalk = !bWalk;
	FRotator CamRot = PlayerCameraManager ? PlayerCameraManager->GetCameraRotation() : FRotator::ZeroRotator;
	if (CamMode == EMorphCamera::Face || CamMode == EMorphCamera::Front || CamMode == EMorphCamera::Side)
	{
		CamRot = O->GetActorRotation();      // inspection cameras: WASD relative to the character
	}
	const FVector Fwd = FRotator(0.f, CamRot.Yaw, 0.f).Vector();
	const FVector Right = FRotator(0.f, CamRot.Yaw + 90.f, 0.f).Vector();
	const FVector Dir = Fwd * In.X + Right * In.Y;
	O->SetMoveInput(FVector2D(Dir.X, Dir.Y), In.IsNearlyZero() ? 0.f : (bWalk ? 0.375f : 1.f));
	O->SetSprint(bShift && !bWalk);
	// ---------------------------------------------------------------- aim: mouse on the ground or a target
	FVector AimPoint = O->GetActorLocation() + O->GetActorForwardVector() * 500.f;
	if (bAimAtTarget && G)
	{
		AimPoint = G->GetAimTargetLocation(SelTarget);
	}
	else
	{
		FVector WL, WD;
		if (DeprojectMousePositionToWorld(WL, WD) && FMath::Abs(WD.Z) > 1e-3f)
		{
			const float GroundZ = O->GetActorLocation().Z;
			const float T = (GroundZ - WL.Z) / WD.Z;
			if (T > 0.f)
			{
				AimPoint = WL + WD * T;
			}
		}
	}
	const bool bRMB = Down(EKeys::RightMouseButton);
	if (Pressed(EKeys::L)) bAimLock = !bAimLock;
	if (Pressed(EKeys::M)) bAimAtTarget = !bAimAtTarget;
	O->SetAimInput(bRMB || bAimLock, AimPoint);
	if (Pressed(EKeys::Tab) && G) SelTarget = (SelTarget + 1) % G->NumTargets();
	if (G)
	{
		FVector Move(0.f);
		if (Down(EKeys::Up)) Move.X += 1.f;
		if (Down(EKeys::Down)) Move.X -= 1.f;
		if (Down(EKeys::Right)) Move.Y += 1.f;
		if (Down(EKeys::Left)) Move.Y -= 1.f;
		if (Down(EKeys::PageUp)) Move.Z += 1.f;
		if (Down(EKeys::PageDown)) Move.Z -= 1.f;
		if (!Move.IsNearlyZero())
		{
			G->MoveTarget(SelTarget, Move * 300.f * Dt);
		}
	}
	// ---------------------------------------------------------------- actions
	if (Pressed(EKeys::SpaceBar)) O->CmdJump();
	if (Pressed(EKeys::Q)) O->CmdDash();
	if (Pressed(EKeys::E)) O->CmdBlink();
	if (Pressed(EKeys::LeftMouseButton)) O->CmdMelee();
	if (Pressed(EKeys::RightMouseButton)) RMBDownTime = GetWorld()->GetTimeSeconds();
	if (RMBDownTime >= 0.f && bRMB && GetWorld()->GetTimeSeconds() - RMBDownTime > 0.35f)
	{
		O->CmdFire(true);
		RMBDownTime = -1.f;
	}
	if (Released(EKeys::RightMouseButton) && RMBDownTime >= 0.f)
	{
		O->CmdFire(false);
		RMBDownTime = -1.f;
	}
	if (Pressed(EKeys::R)) O->CmdReload();
	if (Pressed(EKeys::One)) O->CmdCast(0);
	if (Pressed(EKeys::Two)) O->CmdCast(1);
	if (Pressed(EKeys::Three)) O->CmdCast(2);
	if (Pressed(EKeys::Four)) O->CmdChannel(true);
	if (Released(EKeys::Four)) O->CmdChannel(false);
	if (Pressed(EKeys::X)) O->CmdChannelInterrupt();
	if (Pressed(EKeys::Five)) O->CmdCharge(true);
	if (Released(EKeys::Five)) O->CmdCharge(false);
	if (Pressed(EKeys::C)) O->CmdChargeCancel();
	if (Pressed(EKeys::Six)) O->CmdDeploy();
	if (Pressed(EKeys::Seven)) O->CmdUplink(true);
	if (Released(EKeys::Seven)) O->CmdUplink(false);
	// reactions and disables
	if (Pressed(EKeys::H)) O->CmdHit(bShift ? 1 : -1);
	if (Pressed(EKeys::T)) O->CmdStun();
	if (Pressed(EKeys::K)) O->CmdKnockback();
	if (Pressed(EKeys::U)) O->CmdKnockup();
	if (Pressed(EKeys::J)) O->CmdKnockdown(!bShift);
	if (Pressed(EKeys::N)) O->CmdSleep();
	if (Pressed(EKeys::Delete)) O->CmdDeath(!bShift);
	if (Pressed(EKeys::Z) || Pressed(EKeys::Home)) O->CmdRespawn();
	// social / performance
	if (Pressed(EKeys::G)) O->CmdEmote(TEXT("greet"));
	if (Pressed(EKeys::V)) O->CmdEmote(TEXT("victory"));
	if (Pressed(EKeys::B)) O->CmdEmote(TEXT("defeat"));
	if (Pressed(EKeys::P)) O->CmdDialogue();
	if (Pressed(EKeys::Enter)) O->CmdResume();
	if (Pressed(EKeys::BackSpace)) O->CmdResetCharacter();
	if (Pressed(EKeys::LeftBracket)) O->SetRateScale(O->GetRateScale() - 0.1f);
	if (Pressed(EKeys::RightBracket)) O->SetRateScale(O->GetRateScale() + 0.1f);
	// camera zoom / orbit
	if (Pressed(EKeys::MouseScrollUp)) ArmScale = FMath::Clamp(ArmScale * 0.9f, 0.35f, 3.f);
	if (Pressed(EKeys::MouseScrollDown)) ArmScale = FMath::Clamp(ArmScale * 1.1f, 0.35f, 3.f);
	if (Down(EKeys::Comma)) OrbitYaw -= 90.f * Dt;
	if (Down(EKeys::Period)) OrbitYaw += 90.f * Dt;
}

void AMorphPlayerController::UpdateCamera(float Dt)
{
	AMorphOperative* O = Op();
	USpringArmComponent* Boom = O->CameraBoom;
	UCameraComponent* Cam = O->Camera;
	const float Yaw = O->GetActorRotation().Yaw;
	float Arm = 380.f, Pitch = -15.f, CamYaw = Yaw + OrbitYaw, Fov = 55.f;
	FVector Offset(0.f, 0.f, 40.f);
	switch (CamMode)
	{
	case EMorphCamera::ThirdPerson: break;
	case EMorphCamera::TopDown:
		Arm = 1150.f;
		Pitch = -55.f;
		CamYaw = 45.f + OrbitYaw;
		Offset = FVector(0.f, 0.f, 0.f);
		Fov = 45.f;
		break;
	case EMorphCamera::Side:
		Arm = 330.f;
		Pitch = -4.f;
		CamYaw = Yaw + 90.f + OrbitYaw;
		Offset = FVector(0.f, 0.f, 5.f);
		break;
	case EMorphCamera::Front:
		Arm = 330.f;
		Pitch = -4.f;
		CamYaw = Yaw + 180.f + OrbitYaw;
		Offset = FVector(0.f, 0.f, 5.f);
		break;
	case EMorphCamera::Face:
	{
		// follow the face direction (eyes relative to the head's up axis) so nods and head drops stay framed
		const USkeletalMeshComponent* M = O->GetMesh();
		const FVector H = M->GetSocketLocation(TEXT("head"));
		const FVector Up = (M->GetSocketLocation(TEXT("sock_fx_head")) - H).GetSafeNormal();
		const FVector F = 0.5f * (M->GetSocketLocation(TEXT("eye_l")) + M->GetSocketLocation(TEXT("eye_r"))) - H;
		const FRotator FaceRot = (F - FVector::DotProduct(F, Up) * Up).GetSafeNormal().Rotation();
		Arm = 66.f;
		Pitch = FMath::Clamp(3.f - 0.7f * FaceRot.Pitch, -20.f, 35.f);
		CamYaw = FaceRot.Yaw + 180.f + OrbitYaw;
		Fov = 32.f;
		Offset = O->GetActorTransform().InverseTransformVector(H - O->GetActorLocation()) + FVector(0.f, 0.f, 6.f);   // boom offset is actor-relative
		break;
	}
	case EMorphCamera::Free:
		Arm = 520.f;
		Pitch = -20.f;
		CamYaw = OrbitYaw + 30.f * GetWorld()->GetTimeSeconds();
		break;
	}
	Boom->TargetArmLength = FMath::FInterpTo(Boom->TargetArmLength, Arm * ArmScale, Dt, 6.f);
	FRotator Cur = Boom->GetComponentRotation();
	const FRotator Want(Pitch, CamYaw, 0.f);
	Boom->SetWorldRotation(FMath::RInterpTo(Cur, Want, Dt, CamMode == EMorphCamera::Face ? 10.f : 5.f));
	Boom->SetRelativeLocation(FMath::VInterpTo(Boom->GetRelativeLocation(), Offset, Dt, 8.f));
	Cam->SetFieldOfView(FMath::FInterpTo(Cam->FieldOfView, Fov, Dt, 6.f));
}

void AMorphPlayerController::DrawSkeleton() const
{
	const AMorphOperative* O = Op();
	const USkeletalMeshComponent* M = O->GetMesh();
	const int32 N = M->GetNumBones();
	for (int32 i = 0; i < N; ++i)
	{
		const FName B = M->GetBoneName(i);
		const FName P = M->GetParentBone(B);
		if (P.IsNone())
		{
			continue;
		}
		const bool bSock = B.ToString().StartsWith(TEXT("sock_"));
		DrawDebugLine(GetWorld(), M->GetBoneLocation(P), M->GetBoneLocation(B), bSock ? FColor::Yellow : FColor::Green,
		              false, -1.f, SDPG_Foreground, bSock ? 0.4f : 0.6f);
	}
}
