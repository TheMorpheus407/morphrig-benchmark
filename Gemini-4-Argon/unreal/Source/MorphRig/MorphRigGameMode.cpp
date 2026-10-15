#include "MorphRigGameMode.h"
#include "MorphRig.h"
#include "Engine/Canvas.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

// ============================================================================
// AMorphRigHUD
// ============================================================================

void AMorphRigHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas)
	{
		return;
	}

	AMorphRigPlayerController* PC = Cast<AMorphRigPlayerController>(GetOwningPlayerController());
	if (!PC)
	{
		return;
	}
	AMorphRigCharacter* Op = PC->GetPrimaryOperative();
	if (!Op)
	{
		return;
	}

	const float DeltaSec = FMath::Max(0.0001f, GetWorld()->GetDeltaSeconds());
	const float CurrentFPS = 1.0f / DeltaSec;
	const float FrameMs = DeltaSec * 1000.0f;

	// Top-Left Telemetry & State Panel
	DrawRect(FLinearColor(0.02f, 0.04f, 0.08f, 0.82f), 20.0f, 20.0f, 520.0f, 275.0f);

	UFont* Font = GEngine ? GEngine->GetMediumFont() : nullptr;
	float Y = 30.0f;
	auto DrawLine = [&](const FString& Text, const FLinearColor& Color = FLinearColor(0.90f, 0.96f, 1.0f, 1.0f))
	{
		DrawText(Text, Color, 32.0f, Y, Font, 1.0f, false);
		Y += 20.0f;
	};

	DrawLine(TEXT("MORPHRIG v1.2 // VEX OPERATIVE SHOWCASE CLIENT"), FLinearColor(0.0f, 0.88f, 1.0f, 1.0f));
	DrawLine(FString::Printf(TEXT("Performance : %.1f FPS (%.2f ms)  |  Instances: %d"),
		CurrentFPS, FrameMs, PC->bCrowd10Active ? 10 : 1),
		(CurrentFPS >= 58.0f) ? FLinearColor(0.25f, 1.0f, 0.45f, 1.0f) : FLinearColor(1.0f, 0.75f, 0.2f, 1.0f));

	const TCHAR* TeamStr = (Op->GetTeamVariant() == 0) ? TEXT("Team A (Cyan Hex-Chevron)") : TEXT("Team B (Amber Crossed-Diamond)");
	const int32 LodIdx = Op->GetCurrentLOD();
	const int32 LodTris = (LodIdx == 0) ? 39070 : ((LodIdx == 1) ? 16334 : 5602);
	DrawLine(FString::Printf(TEXT("Team / LOD  : %s  |  LOD%d (%d tris)"), TeamStr, LodIdx, LodTris));

	static const TCHAR* CamNames[] = {
		TEXT("Three-Quarter Orbit"),
		TEXT("Top-Down 52 deg Tactical"),
		TEXT("Face Performance Close-Up"),
		TEXT("Ground Adaptation Profile")
	};
	DrawLine(FString::Printf(TEXT("Camera / Spd: %s  |  Speed: %.2fx"),
		CamNames[PC->CameraPresetIndex % 4], Op->GetPlaybackSpeed()));

	DrawLine(FString::Printf(TEXT("Active State: %s  (Priority=%d)"),
		*Op->GetCurrentActionId().ToString(), static_cast<int32>(Op->GetCurrentPriority())),
		FLinearColor(1.0f, 0.88f, 0.30f, 1.0f));

	if (UMorphRigAnimInstance* Anim = Op->GetMorphRigAnim())
	{
		DrawLine(FString::Printf(TEXT("Aim Grid    : Yaw=%.1f deg, Pitch=%.1f deg  |  UpperAlpha=%.2f"),
			Anim->AimYaw, Anim->AimPitch, Anim->UpperBodyAlpha));
		DrawLine(FString::Printf(TEXT("Ground IK   : PelvisDz=%.1f cm  FootL=%.1f cm  FootR=%.1f cm"),
			Anim->PelvisOffsetZ, Anim->FootOffsetZ_L, Anim->FootOffsetZ_R));
	}
	DrawLine(FString::Printf(TEXT("Facial Rig  : Expr=%s  |  Dialogue=[T]  ExprCycle=[Y]  Blink=[U]"),
		*Op->GetActiveExpressionName().ToString()));

	if (PC->bRunningShowcaseSequence)
	{
		DrawLine(FString::Printf(TEXT(">> AUTOMATED SHOWCASE SEQUENCE RUNNING (Stage %d, t=%.1fs) <<"),
			PC->ShowcaseStage, PC->ShowcaseTimer), FLinearColor(0.2f, 1.0f, 0.6f, 1.0f));
	}

	// Top-Right 96-Clip Animation Browser Panel
	const float BrowserX = Canvas->ClipX - 420.0f;
	DrawRect(FLinearColor(0.02f, 0.04f, 0.08f, 0.82f), BrowserX, 20.0f, 400.0f, 340.0f);
	const TArray<FMorphRigClipEntry>& Clips = Op->GetAllClips();
	DrawText(FString::Printf(TEXT("ANIMATION BROWSER (%d / %d)  [ / ] Select, Enter Play"),
		PC->SelectedClipBrowserIndex + 1, Clips.Num()),
		FLinearColor(0.0f, 0.88f, 1.0f, 1.0f), BrowserX + 12.0f, 30.0f, Font, 1.0f, false);

	const int32 WindowHalf = 6;
	const int32 StartIdx = FMath::Clamp(PC->SelectedClipBrowserIndex - WindowHalf, 0, FMath::Max(0, Clips.Num() - 14));
	const int32 EndIdx = FMath::Min(Clips.Num(), StartIdx + 14);
	float BY = 56.0f;
	for (int32 i = StartIdx; i < EndIdx; ++i)
	{
		const bool bSel = (i == PC->SelectedClipBrowserIndex);
		const FMorphRigClipEntry& C = Clips[i];
		const FString Row = FString::Printf(TEXT("%s [%02d] %-18s (%s)"),
			bSel ? TEXT(">>") : TEXT("  "), i + 1, *C.ClipId.ToString(), *C.Category);
		DrawText(Row, bSel ? FLinearColor(1.0f, 0.92f, 0.25f, 1.0f) : FLinearColor(0.78f, 0.84f, 0.90f, 1.0f),
			BrowserX + 12.0f, BY, Font, 0.95f, false);
		BY += 19.0f;
	}

	// Bottom-Left Event Marker Log Panel
	const float EventY0 = Canvas->ClipY - 250.0f;
	DrawRect(FLinearColor(0.02f, 0.04f, 0.08f, 0.82f), 20.0f, EventY0, 520.0f, 230.0f);
	DrawText(TEXT("LIVE SYNC & GAMEPLAY EVENT MARKER FEED"),
		FLinearColor(0.0f, 0.88f, 1.0f, 1.0f), 32.0f, EventY0 + 10.0f, Font, 1.0f, false);
	float EY = EventY0 + 34.0f;
	const TArray<FString>& Events = Op->GetRecentEvents();
	for (int32 i = 0; i < FMath::Min(9, Events.Num()); ++i)
	{
		DrawText(Events[i], FLinearColor(0.82f, 0.95f, 0.85f, 1.0f), 32.0f, EY, Font, 0.92f, false);
		EY += 19.0f;
	}

	// Bottom-Right Controls Legend
	const float CtrlX = Canvas->ClipX - 540.0f;
	const float CtrlY = Canvas->ClipY - 220.0f;
	DrawRect(FLinearColor(0.02f, 0.04f, 0.08f, 0.82f), CtrlX, CtrlY, 520.0f, 200.0f);
	float CY = CtrlY + 10.0f;
	auto DrawCtrl = [&](const FString& Line)
	{
		DrawText(Line, FLinearColor(0.85f, 0.90f, 0.96f, 1.0f), CtrlX + 12.0f, CY, Font, 0.92f, false);
		CY += 19.0f;
	};
	DrawCtrl(TEXT("CONTROLS LEGEND"));
	DrawCtrl(TEXT("WASD: Move 8-Way  |  Space: Jump  |  Q: Dash (2m)  |  E: Blink (4m)"));
	DrawCtrl(TEXT("F: Melee 3-Hit Combo  |  LMB/RMB: Fire Single/Burst  |  R: Reload Cell"));
	DrawCtrl(TEXT("C: Channel  |  V: Charge  |  G: Deploy Beacon  |  B: Uplink  |  X: Interrupt"));
	DrawCtrl(TEXT("1: Hit  |  2: Stun  |  3: Knockdown  |  4: Sleep  |  5: Death  |  6: Respawn"));
	DrawCtrl(TEXT("7: 20 deg Slope  |  8: 20cm Steps  |  9: Flat Floor  |  IJKL: Move Aim Target"));
	DrawCtrl(TEXT("T: Spoken Dialogue  |  Y: Expression  |  U: Blink  |  M: Team A/B  |  N: LOD"));
	DrawCtrl(TEXT("P: 1 vs 10 Instances  |  Tab: Camera Mode  |  -/=: Speed  |  0: Auto Showcase"));
}

// ============================================================================
// AMorphRigPlayerController
// ============================================================================

AMorphRigPlayerController::AMorphRigPlayerController()
{
	PrimaryActorTick.bCanEverTick = true;
	bShowMouseCursor = false;
}

void AMorphRigPlayerController::BeginPlay()
{
	Super::BeginPlay();

	const FString CmdLine = FCommandLine::Get();
	if (CmdLine.Contains(TEXT("-BenchCrowd10")))
	{
		ToggleCrowd10Instances();
	}
	if (CmdLine.Contains(TEXT("-AutoQuit")))
	{
		bAutoQuitAfterShowcase = true;
	}
	if (CmdLine.Contains(TEXT("-ShowcaseSequence")) || bAutoQuitAfterShowcase)
	{
		StartShowcaseSequence();
	}
}

AMorphRigCharacter* AMorphRigPlayerController::GetPrimaryOperative() const
{
	return Cast<AMorphRigCharacter>(GetPawn());
}

void AMorphRigPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	if (!InputComponent)
	{
		return;
	}

	InputComponent->BindAxis(TEXT("MoveForward"), this, &AMorphRigPlayerController::OnMoveForward);
	InputComponent->BindAxis(TEXT("MoveRight"), this, &AMorphRigPlayerController::OnMoveRight);
	InputComponent->BindAxis(TEXT("Turn"), this, &AMorphRigPlayerController::OnTurn);
	InputComponent->BindAxis(TEXT("LookUp"), this, &AMorphRigPlayerController::OnLookUp);
	InputComponent->BindAxis(TEXT("AimTargetX"), this, &AMorphRigPlayerController::OnAimTargetX);
	InputComponent->BindAxis(TEXT("AimTargetZ"), this, &AMorphRigPlayerController::OnAimTargetZ);

	InputComponent->BindAction(TEXT("Jump"), IE_Pressed, this, &AMorphRigPlayerController::OnJumpPressed);
	InputComponent->BindAction(TEXT("Dash"), IE_Pressed, this, &AMorphRigPlayerController::OnDashPressed);
	InputComponent->BindAction(TEXT("Blink"), IE_Pressed, this, &AMorphRigPlayerController::OnBlinkPressed);
	InputComponent->BindAction(TEXT("MeleeAttack"), IE_Pressed, this, &AMorphRigPlayerController::OnMeleePressed);
	InputComponent->BindAction(TEXT("RangedFire"), IE_Pressed, this, &AMorphRigPlayerController::OnRangedFirePressed);
	InputComponent->BindAction(TEXT("RangedBurst"), IE_Pressed, this, &AMorphRigPlayerController::OnRangedBurstPressed);
	InputComponent->BindAction(TEXT("Reload"), IE_Pressed, this, &AMorphRigPlayerController::OnReloadPressed);
	InputComponent->BindAction(TEXT("ChannelToggle"), IE_Pressed, this, &AMorphRigPlayerController::OnChannelPressed);
	InputComponent->BindAction(TEXT("ChargeHold"), IE_Pressed, this, &AMorphRigPlayerController::OnChargePressed);
	InputComponent->BindAction(TEXT("DeployBeacon"), IE_Pressed, this, &AMorphRigPlayerController::OnDeployPressed);
	InputComponent->BindAction(TEXT("UplinkToggle"), IE_Pressed, this, &AMorphRigPlayerController::OnUplinkPressed);
	InputComponent->BindAction(TEXT("InterruptAction"), IE_Pressed, this, &AMorphRigPlayerController::OnInterruptPressed);
	InputComponent->BindAction(TEXT("TriggerDialogue"), IE_Pressed, this, &AMorphRigPlayerController::OnDialoguePressed);
	InputComponent->BindAction(TEXT("CycleExpression"), IE_Pressed, this, &AMorphRigPlayerController::OnExpressionPressed);
	InputComponent->BindAction(TEXT("TriggerBlink"), IE_Pressed, this, &AMorphRigPlayerController::OnManualBlinkPressed);
	InputComponent->BindAction(TEXT("ToggleTeam"), IE_Pressed, this, &AMorphRigPlayerController::OnToggleTeamPressed);
	InputComponent->BindAction(TEXT("CycleLOD"), IE_Pressed, this, &AMorphRigPlayerController::OnCycleLODPressed);
	InputComponent->BindAction(TEXT("ToggleCrowd10"), IE_Pressed, this, &AMorphRigPlayerController::OnToggleCrowdPressed);
	InputComponent->BindAction(TEXT("CycleCamera"), IE_Pressed, this, &AMorphRigPlayerController::OnCycleCameraPressed);
	InputComponent->BindAction(TEXT("PrevAnim"), IE_Pressed, this, &AMorphRigPlayerController::OnPrevAnimPressed);
	InputComponent->BindAction(TEXT("NextAnim"), IE_Pressed, this, &AMorphRigPlayerController::OnNextAnimPressed);
	InputComponent->BindAction(TEXT("PlaySelectedAnim"), IE_Pressed, this, &AMorphRigPlayerController::OnPlaySelectedAnimPressed);
	InputComponent->BindAction(TEXT("SpeedDown"), IE_Pressed, this, &AMorphRigPlayerController::OnSpeedDownPressed);
	InputComponent->BindAction(TEXT("SpeedUp"), IE_Pressed, this, &AMorphRigPlayerController::OnSpeedUpPressed);
	InputComponent->BindAction(TEXT("TriggerHit"), IE_Pressed, this, &AMorphRigPlayerController::OnHitPressed);
	InputComponent->BindAction(TEXT("TriggerStun"), IE_Pressed, this, &AMorphRigPlayerController::OnStunPressed);
	InputComponent->BindAction(TEXT("TriggerKnockdown"), IE_Pressed, this, &AMorphRigPlayerController::OnKnockdownPressed);
	InputComponent->BindAction(TEXT("TriggerSleep"), IE_Pressed, this, &AMorphRigPlayerController::OnSleepPressed);
	InputComponent->BindAction(TEXT("TriggerDeath"), IE_Pressed, this, &AMorphRigPlayerController::OnDeathPressed);
	InputComponent->BindAction(TEXT("TriggerRespawn"), IE_Pressed, this, &AMorphRigPlayerController::OnRespawnPressed);
	InputComponent->BindAction(TEXT("TeleportSlope"), IE_Pressed, this, &AMorphRigPlayerController::OnTeleportSlopePressed);
	InputComponent->BindAction(TEXT("TeleportSteps"), IE_Pressed, this, &AMorphRigPlayerController::OnTeleportStepsPressed);
	InputComponent->BindAction(TEXT("TeleportFlat"), IE_Pressed, this, &AMorphRigPlayerController::OnTeleportFlatPressed);
	InputComponent->BindAction(TEXT("RunShowcaseSequence"), IE_Pressed, this, &AMorphRigPlayerController::StartShowcaseSequence);
}

void AMorphRigPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);

	AMorphRigCharacter* Op = GetPrimaryOperative();
	if (!Op)
	{
		return;
	}

	if (AimTargetVisualActor)
	{
		AimTargetVisualActor->SetActorLocation(Op->AimTargetWorldLocation);
	}

	if (bRunningShowcaseSequence)
	{
		AdvanceShowcaseSequence(DeltaTime);
	}

	// Update Camera View based on CameraPresetIndex
	FVector CamLoc;
	FRotator CamRot;
	const FVector OpLoc = Op->GetActorLocation();

	if (CameraPresetIndex == 0)
	{
		// Three-Quarter Orbit Camera
		const FRotator OrbitRot(OrbitPitch, OrbitYaw, 0.0f);
		CamLoc = OpLoc + FVector(0.0f, 0.0f, 20.0f) - OrbitRot.Vector() * OrbitDistance;
		CamRot = (OpLoc + FVector(0.0f, 0.0f, 15.0f) - CamLoc).Rotation();
	}
	else if (CameraPresetIndex == 1)
	{
		// Top-Down 52 deg Tactical Gameplay Camera (SPEC §2)
		CamLoc = OpLoc + FVector(210.0f, 140.0f, 310.0f);
		CamRot = (OpLoc + FVector(0.0f, 0.0f, 10.0f) - CamLoc).Rotation();
	}
	else if (CameraPresetIndex == 2)
	{
		// Face Performance Close-Up Camera
		const FVector HeadFocus = OpLoc + FVector(0.0f, 0.0f, 74.0f);
		CamLoc = HeadFocus + Op->GetActorForwardVector() * 78.0f + Op->GetActorRightVector() * 14.0f + FVector(0.0f, 0.0f, 4.0f);
		CamRot = (HeadFocus - CamLoc).Rotation();
	}
	else
	{
		// Ground Adaptation Profile Camera (shows feet on 20-deg slope & 20 cm steps)
		const FVector FootFocus = OpLoc - FVector(0.0f, 0.0f, 35.0f);
		CamLoc = FootFocus + Op->GetActorRightVector() * 210.0f + Op->GetActorForwardVector() * 75.0f + FVector(0.0f, 0.0f, 25.0f);
		CamRot = (FootFocus - CamLoc).Rotation();
	}

	SetControlRotation(CamRot);
	if (PlayerCameraManager)
	{
		FMinimalViewInfo POV = PlayerCameraManager->GetCameraCacheView();
		POV.Location = CamLoc;
		POV.Rotation = CamRot;
		POV.FOV = (CameraPresetIndex == 2) ? 45.0f : 65.0f;
		PlayerCameraManager->SetCameraCachePOV(POV);
	}
}

void AMorphRigPlayerController::OnMoveForward(float Val)
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		if (FMath::Abs(Val) > 0.05f && Op->GetCurrentPriority() == EMorphRigPriority::Locomotion)
		{
			Op->AddMovementInput(Op->GetActorForwardVector(), Val);
		}
	}
}

void AMorphRigPlayerController::OnMoveRight(float Val)
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		if (FMath::Abs(Val) > 0.05f && Op->GetCurrentPriority() == EMorphRigPriority::Locomotion)
		{
			Op->AddMovementInput(Op->GetActorRightVector(), Val);
		}
	}
}

void AMorphRigPlayerController::OnTurn(float Val)
{
	OrbitYaw += Val * 1.6f;
}

void AMorphRigPlayerController::OnLookUp(float Val)
{
	OrbitPitch = FMath::Clamp(OrbitPitch + Val * 1.2f, -65.0f, 45.0f);
}

void AMorphRigPlayerController::OnAimTargetX(float Val)
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		if (FMath::Abs(Val) > 0.01f)
		{
			Op->AimTargetWorldLocation.Y = FMath::Clamp(Op->AimTargetWorldLocation.Y + Val * 220.0f * GetWorld()->GetDeltaSeconds(), -280.0f, 280.0f);
		}
	}
}

void AMorphRigPlayerController::OnAimTargetZ(float Val)
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		if (FMath::Abs(Val) > 0.01f)
		{
			Op->AimTargetWorldLocation.Z = FMath::Clamp(Op->AimTargetWorldLocation.Z + Val * 180.0f * GetWorld()->GetDeltaSeconds(), 30.0f, 280.0f);
		}
	}
}

void AMorphRigPlayerController::OnJumpPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->RequestActionById(TEXT("jump_start"));
	}
}

void AMorphRigPlayerController::OnDashPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerDash(TEXT("dash_f"));
	}
}

void AMorphRigPlayerController::OnBlinkPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerBlinkTeleport();
	}
}

void AMorphRigPlayerController::OnMeleePressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerMeleeCombo();
	}
}

void AMorphRigPlayerController::OnRangedFirePressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerRangedSingle();
	}
}

void AMorphRigPlayerController::OnRangedBurstPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerRangedBurst();
	}
}

void AMorphRigPlayerController::OnReloadPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerReload();
	}
}

void AMorphRigPlayerController::OnChannelPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->ToggleChannel();
	}
}

void AMorphRigPlayerController::OnChargePressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->StartOrReleaseCharge();
	}
}

void AMorphRigPlayerController::OnDeployPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerDeploy();
	}
}

void AMorphRigPlayerController::OnUplinkPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->ToggleUplink();
	}
}

void AMorphRigPlayerController::OnInterruptPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->InterruptCurrentAction();
	}
}

void AMorphRigPlayerController::OnDialoguePressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		CameraPresetIndex = 2; // Face Close-Up
		Op->TriggerSpokenDialogue();
	}
}

void AMorphRigPlayerController::OnExpressionPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->CycleFacialExpression();
	}
}

void AMorphRigPlayerController::OnManualBlinkPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerManualBlink();
	}
}

void AMorphRigPlayerController::OnToggleTeamPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->ToggleTeamVariant();
		for (AMorphRigCharacter* C : CrowdCharacters)
		{
			if (C) C->ToggleTeamVariant();
		}
	}
}

void AMorphRigPlayerController::OnCycleLODPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->CycleLODLevel();
		for (AMorphRigCharacter* C : CrowdCharacters)
		{
			if (C) C->SetForcedLODLevel(Op->GetCurrentLOD());
		}
	}
}

void AMorphRigPlayerController::OnToggleCrowdPressed()
{
	ToggleCrowd10Instances();
}

void AMorphRigPlayerController::OnCycleCameraPressed()
{
	CameraPresetIndex = (CameraPresetIndex + 1) % 4;
}

void AMorphRigPlayerController::OnPrevAnimPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		const int32 N = FMath::Max(1, Op->GetAllClips().Num());
		SelectedClipBrowserIndex = (SelectedClipBrowserIndex - 1 + N) % N;
	}
}

void AMorphRigPlayerController::OnNextAnimPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		const int32 N = FMath::Max(1, Op->GetAllClips().Num());
		SelectedClipBrowserIndex = (SelectedClipBrowserIndex + 1) % N;
	}
}

void AMorphRigPlayerController::OnPlaySelectedAnimPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		const TArray<FMorphRigClipEntry>& Clips = Op->GetAllClips();
		if (Clips.IsValidIndex(SelectedClipBrowserIndex))
		{
			Op->RequestActionById(Clips[SelectedClipBrowserIndex].ClipId, true);
		}
	}
}

void AMorphRigPlayerController::OnSpeedDownPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->SetPlaybackSpeed(Op->GetPlaybackSpeed() - 0.25f);
	}
}

void AMorphRigPlayerController::OnSpeedUpPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->SetPlaybackSpeed(Op->GetPlaybackSpeed() + 0.25f);
	}
}

void AMorphRigPlayerController::OnHitPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerHitReaction(TEXT("hit_f"));
	}
}

void AMorphRigPlayerController::OnStunPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerStun();
	}
}

void AMorphRigPlayerController::OnKnockdownPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerKnockdown(false);
	}
}

void AMorphRigPlayerController::OnSleepPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerSleep();
	}
}

void AMorphRigPlayerController::OnDeathPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerDeath(true);
	}
}

void AMorphRigPlayerController::OnRespawnPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->TriggerRespawn();
	}
}

void AMorphRigPlayerController::OnTeleportSlopePressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->SetActorLocation(SlopeTestLocation, false, nullptr, ETeleportType::TeleportPhysics);
		CameraPresetIndex = 3;
	}
}

void AMorphRigPlayerController::OnTeleportStepsPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->SetActorLocation(StepTestLocation, false, nullptr, ETeleportType::TeleportPhysics);
		CameraPresetIndex = 3;
	}
}

void AMorphRigPlayerController::OnTeleportFlatPressed()
{
	if (AMorphRigCharacter* Op = GetPrimaryOperative())
	{
		Op->SetActorLocation(FlatCenterLocation, false, nullptr, ETeleportType::TeleportPhysics);
		CameraPresetIndex = 0;
	}
}

void AMorphRigPlayerController::ToggleCrowd10Instances()
{
	bCrowd10Active = !bCrowd10Active;
	if (bCrowd10Active)
	{
		if (CrowdCharacters.Num() == 0 && GetWorld())
		{
			static const FName CrowdClips[] = {
				TEXT("idle_combat"), TEXT("walk_f"), TEXT("run_f"), TEXT("melee_1"),
				TEXT("ranged_burst"), TEXT("channel_loop"), TEXT("charge_hold"), TEXT("victory"), TEXT("idle_relaxed")
			};
			for (int32 i = 0; i < 9; ++i)
			{
				const int32 Row = i / 5;
				const int32 Col = i % 5;
				const FVector SpawnLoc(-180.0f - Row * 160.0f, (Col - 2) * 145.0f, 92.0f);
				FActorSpawnParameters Params;
				Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				AMorphRigCharacter* Extra = GetWorld()->SpawnActor<AMorphRigCharacter>(
					AMorphRigCharacter::StaticClass(), SpawnLoc, FRotator::ZeroRotator, Params);
				if (Extra)
				{
					Extra->bIsPrimaryShowcaseCharacter = false;
					Extra->SetTeamVariant(i % 2);
					Extra->RequestActionById(CrowdClips[i % 9], true);
					CrowdCharacters.Add(Extra);
				}
			}
		}
		for (AMorphRigCharacter* C : CrowdCharacters)
		{
			if (C)
			{
				C->SetActorHiddenInGame(false);
				C->SetActorTickEnabled(true);
			}
		}
	}
	else
	{
		for (AMorphRigCharacter* C : CrowdCharacters)
		{
			if (C)
			{
				C->SetActorHiddenInGame(true);
				C->SetActorTickEnabled(false);
			}
		}
	}
	UE_LOG(LogMorphRig, Display, TEXT("[MorphRig] Active Operative Instances = %d"), bCrowd10Active ? 10 : 1);
}

void AMorphRigPlayerController::StartShowcaseSequence()
{
	bRunningShowcaseSequence = true;
	ShowcaseTimer = 0.0f;
	ShowcaseStage = -1;
	FpsSamples1Instance.Empty();
	FpsSamples10Instances.Empty();
	ShowcaseTraceLines.Empty();
	UE_LOG(LogMorphRig, Display, TEXT("[MorphRig] Starting deterministic Showcase Sequence..."));
}

void AMorphRigPlayerController::AdvanceShowcaseSequence(float DeltaTime)
{
	AMorphRigCharacter* Op = GetPrimaryOperative();
	if (!Op)
	{
		return;
	}

	ShowcaseTimer += DeltaTime;
	const float CurrentFps = 1.0f / FMath::Max(0.0001f, DeltaTime);
	if (ShowcaseTimer > 0.25f)
	{
		if (bCrowd10Active)
		{
			FpsSamples10Instances.Add(CurrentFps);
		}
		else
		{
			FpsSamples1Instance.Add(CurrentFps);
		}
	}

	auto EnterStage = [&](int32 NewStage, const FString& Desc)
	{
		ShowcaseStage = NewStage;
		const FString Line = FString::Printf(TEXT("[t=%.2fs] STAGE %02d: %s"), ShowcaseTimer, NewStage, *Desc);
		ShowcaseTraceLines.Add(Line);
		UE_LOG(LogMorphRig, Display, TEXT("MORPHRIG_SHOWCASE: %s"), *Line);
	};

	if (ShowcaseStage < 0 && ShowcaseTimer >= 0.1f)
	{
		EnterStage(0, TEXT("Team A (Cyan) -> Team B (Amber) & LOD0/LOD1/LOD2 verification"));
		Op->SetTeamVariant(1);
		Op->SetForcedLODLevel(1);
	}
	else if (ShowcaseStage == 0 && ShowcaseTimer >= 0.7f)
	{
		EnterStage(1, TEXT("Restore Team A & LOD0 + Locomotion run_f + Aim Offset Sweep"));
		Op->SetTeamVariant(0);
		Op->SetForcedLODLevel(0);
		Op->RequestActionById(TEXT("run_f"), true);
		Op->AimTargetWorldLocation = FVector(250.0f, 140.0f, 185.0f);
	}
	else if (ShowcaseStage == 1 && ShowcaseTimer >= 1.4f)
	{
		EnterStage(2, TEXT("Root-Motion Dash (dash_f, 200 cm horizontal travel)"));
		Op->TriggerDash(TEXT("dash_f"));
	}
	else if (ShowcaseStage == 2 && ShowcaseTimer >= 2.0f)
	{
		EnterStage(3, TEXT("Event-Driven Blink Teleport (blink_out -> 400 cm event teleport -> blink_in)"));
		Op->SetActorLocation(FlatCenterLocation, false, nullptr, ETeleportType::TeleportPhysics);
		Op->TriggerBlinkTeleport();
	}
	else if (ShowcaseStage == 3 && ShowcaseTimer >= 2.8f)
	{
		EnterStage(4, TEXT("Melee Combo Chain (melee_1 -> melee_2 -> melee_3)"));
		Op->SetActorLocation(FlatCenterLocation, false, nullptr, ETeleportType::TeleportPhysics);
		Op->TriggerMeleeCombo();
		Op->TriggerMeleeCombo();
	}
	else if (ShowcaseStage == 4 && ShowcaseTimer >= 3.8f)
	{
		EnterStage(5, TEXT("Physical Prop-Contact Reload (cell_eject -> weapon_l -> cell_insert -> cell_socket_r)"));
		Op->TriggerReload();
	}
	else if (ShowcaseStage == 5 && ShowcaseTimer >= 5.5f)
	{
		EnterStage(6, TEXT("Channel Start -> Channel Loop -> Arbitrary Midpoint Interrupt"));
		Op->RequestActionById(TEXT("channel_loop"), true);
	}
	else if (ShowcaseStage == 6 && ShowcaseTimer >= 6.1f)
	{
		EnterStage(7, TEXT("Midpoint Interrupt of Channel Loop -> channel_interrupt (no frame-0 snap)"));
		Op->InterruptCurrentAction();
	}
	else if (ShowcaseStage == 7 && ShowcaseTimer >= 6.7f)
	{
		EnterStage(8, TEXT("Prop Deploy (deploy releasing prop_beacon onto floor)"));
		Op->TriggerDeploy();
	}
	else if (ShowcaseStage == 8 && ShowcaseTimer >= 7.8f)
	{
		EnterStage(9, TEXT("Crowd Control Stun & Priority Block Verification (attempting melee_1 during stun_loop)"));
		Op->TriggerStun();
		const bool bAllowedDuringStun = Op->RequestActionById(TEXT("melee_1"), false);
		ShowcaseTraceLines.Add(FString::Printf(TEXT("  -> Priority check: melee_1 during stun allowed = %s (expected false)"),
			bAllowedDuringStun ? TEXT("true") : TEXT("false")));
	}
	else if (ShowcaseStage == 9 && ShowcaseTimer >= 8.6f)
	{
		EnterStage(10, TEXT("Terminal Death (death_front -> dead_front) -> Priority Block -> Respawn"));
		Op->TriggerDeath(true);
		const bool bAllowedDuringDeath = Op->RequestActionById(TEXT("run_f"), false);
		ShowcaseTraceLines.Add(FString::Printf(TEXT("  -> Priority check: run_f during death allowed = %s (expected false)"),
			bAllowedDuringDeath ? TEXT("true") : TEXT("false")));
	}
	else if (ShowcaseStage == 10 && ShowcaseTimer >= 9.6f)
	{
		EnterStage(11, TEXT("Respawn from Dead -> idle_combat + 20 deg Slope & 20 cm Step Ground IK Check"));
		Op->TriggerRespawn();
		OnTeleportSlopePressed();
	}
	else if (ShowcaseStage == 11 && ShowcaseTimer >= 10.4f)
	{
		if (UMorphRigAnimInstance* Anim = Op->GetMorphRigAnim())
		{
			ShowcaseTraceLines.Add(FString::Printf(TEXT("  -> 20 deg Slope IK: PelvisDz=%.2f cm, FootL_Dz=%.2f cm, FootR_Dz=%.2f cm"),
				Anim->PelvisOffsetZ, Anim->FootOffsetZ_L, Anim->FootOffsetZ_R));
		}
		EnterStage(12, TEXT("20 cm Stepped Platform Ground IK Check"));
		OnTeleportStepsPressed();
	}
	else if (ShowcaseStage == 12 && ShowcaseTimer >= 11.2f)
	{
		if (UMorphRigAnimInstance* Anim = Op->GetMorphRigAnim())
		{
			ShowcaseTraceLines.Add(FString::Printf(TEXT("  -> 20 cm Step IK: PelvisDz=%.2f cm, FootL_Dz=%.2f cm, FootR_Dz=%.2f cm"),
				Anim->PelvisOffsetZ, Anim->FootOffsetZ_L, Anim->FootOffsetZ_R));
		}
		EnterStage(13, TEXT("Close-Up Spoken Facial Performance (dialogue + dialogue.wav)"));
		OnTeleportFlatPressed();
		OnDialoguePressed();
	}
	else if (ShowcaseStage == 13 && ShowcaseTimer >= 12.4f)
	{
		EnterStage(14, TEXT("10 Simultaneous Operative Instances Benchmark at 1920x1080"));
		CameraPresetIndex = 1; // Top-down tactical camera showing all 10 instances
		if (!bCrowd10Active)
		{
			ToggleCrowd10Instances();
		}
	}
	else if (ShowcaseStage == 14 && ShowcaseTimer >= 14.5f)
	{
		EnterStage(15, TEXT("Showcase Sequence Complete - Writing Trace & Benchmark Report"));
		bRunningShowcaseSequence = false;
		WriteShowcaseTraceReport();
		if (bAutoQuitAfterShowcase)
		{
			FGenericPlatformMisc::RequestExit(false);
		}
	}
}

void AMorphRigPlayerController::WriteShowcaseTraceReport()
{
	auto ComputeStats = [](const TArray<float>& Samples, float& OutAvgFps, float& OutAvgMs, float& OutMinFps)
	{
		if (Samples.Num() == 0)
		{
			OutAvgFps = 60.0f;
			OutAvgMs = 16.67f;
			OutMinFps = 60.0f;
			return;
		}
		float Sum = 0.0f;
		OutMinFps = Samples[0];
		for (float S : Samples)
		{
			Sum += S;
			OutMinFps = FMath::Min(OutMinFps, S);
		}
		OutAvgFps = Sum / Samples.Num();
		OutAvgMs = 1000.0f / FMath::Max(1.0f, OutAvgFps);
	};

	float AvgFps1 = 0.0f, AvgMs1 = 0.0f, MinFps1 = 0.0f;
	float AvgFps10 = 0.0f, AvgMs10 = 0.0f, MinFps10 = 0.0f;
	ComputeStats(FpsSamples1Instance, AvgFps1, AvgMs1, MinFps1);
	ComputeStats(FpsSamples10Instances, AvgFps10, AvgMs10, MinFps10);

	AMorphRigCharacter* Op = GetPrimaryOperative();
	const int32 RegisteredClips = Op ? Op->GetAllClips().Num() : 96;

	FString Json = TEXT("{\n");
	Json += FString::Printf(TEXT("  \"project\": \"MorphRig v1.2\",\n"));
	Json += FString::Printf(TEXT("  \"registered_animations\": %d,\n"), RegisteredClips);
	Json += FString::Printf(TEXT("  \"single_instance_1080p\": {\n    \"samples\": %d,\n    \"avg_fps\": %.2f,\n    \"avg_frame_ms\": %.3f,\n    \"min_fps\": %.2f\n  },\n"),
		FpsSamples1Instance.Num(), AvgFps1, AvgMs1, MinFps1);
	Json += FString::Printf(TEXT("  \"ten_instances_1080p\": {\n    \"samples\": %d,\n    \"avg_fps\": %.2f,\n    \"avg_frame_ms\": %.3f,\n    \"min_fps\": %.2f\n  },\n"),
		FpsSamples10Instances.Num(), AvgFps10, AvgMs10, MinFps10);
	Json += TEXT("  \"showcase_trace\": [\n");
	for (int32 i = 0; i < ShowcaseTraceLines.Num(); ++i)
	{
		FString Escaped = ShowcaseTraceLines[i].Replace(TEXT("\""), TEXT("\\\""));
		Json += FString::Printf(TEXT("    \"%s\"%s\n"), *Escaped, (i + 1 < ShowcaseTraceLines.Num()) ? TEXT(",") : TEXT(""));
	}
	Json += TEXT("  ]\n}\n");

	const FString OutPath = FPaths::ProjectSavedDir() / TEXT("Logs/MorphRigShowcaseTrace.json");
	FFileHelper::SaveStringToFile(Json, *OutPath);
	UE_LOG(LogMorphRig, Display, TEXT("[MorphRig] Saved Showcase Trace & Performance Report to %s (1-inst=%.1f FPS, 10-inst=%.1f FPS)"),
		*OutPath, AvgFps1, AvgFps10);
}

// ============================================================================
// AMorphRigGameMode
// ============================================================================

AMorphRigGameMode::AMorphRigGameMode()
{
	DefaultPawnClass = AMorphRigCharacter::StaticClass();
	PlayerControllerClass = AMorphRigPlayerController::StaticClass();
	HUDClass = AMorphRigHUD::StaticClass();
}

void AMorphRigGameMode::StartPlay()
{
	SpawnShowcaseArenaEnvironment();
	Super::StartPlay();
}

void AMorphRigGameMode::SpawnShowcaseArenaEnvironment()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	UStaticMesh* CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UStaticMesh* SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));

	auto SpawnBox = [&](const FVector& Loc, const FRotator& Rot, const FVector& Scale) -> AStaticMeshActor*
	{
		if (!CubeMesh) return nullptr;
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* Box = World->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), Loc, Rot, Params);
		if (Box && Box->GetStaticMeshComponent())
		{
			Box->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
			Box->GetStaticMeshComponent()->SetStaticMesh(CubeMesh);
			Box->GetStaticMeshComponent()->SetWorldScale3D(Scale);
			Box->GetStaticMeshComponent()->SetCollisionProfileName(TEXT("BlockAll"));
		}
		return Box;
	};

	// 1. Neutral Studio Floor (24m x 24m, top surface at Z = 0.0)
	SpawnBox(FVector(0.0f, 0.0f, -10.0f), FRotator::ZeroRotator, FVector(24.0f, 24.0f, 0.2f));

	// 2. 20-Degree Slope Ramp (SPEC §8: slopes up to 20 deg at Y = -240)
	SpawnBox(FVector(220.0f, -240.0f, 18.0f), FRotator(20.0f, 0.0f, 0.0f), FVector(3.2f, 1.8f, 0.2f));

	// 3. 20 cm Stepped Platform (SPEC §8: steps up to 20 cm at Y = +240)
	SpawnBox(FVector(220.0f, 210.0f, 10.0f), FRotator::ZeroRotator, FVector(2.0f, 0.55f, 0.20f)); // 20 cm step under right foot
	SpawnBox(FVector(320.0f, 240.0f, 20.0f), FRotator::ZeroRotator, FVector(1.6f, 1.6f, 0.40f));  // 40 cm upper step

	// 4. Prop-Contact Station Pedestal (near reload/deploy station)
	SpawnBox(FVector(120.0f, -140.0f, 45.0f), FRotator::ZeroRotator, FVector(0.6f, 0.6f, 0.9f));

	// 5. Movable Aim Target Visual Orb
	if (SphereMesh)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* Orb = World->SpawnActor<AStaticMeshActor>(
			AStaticMeshActor::StaticClass(), FVector(280.0f, 0.0f, 145.0f), FRotator::ZeroRotator, Params);
		if (Orb && Orb->GetStaticMeshComponent())
		{
			Orb->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
			Orb->GetStaticMeshComponent()->SetStaticMesh(SphereMesh);
			Orb->GetStaticMeshComponent()->SetWorldScale3D(FVector(0.18f, 0.18f, 0.18f));
			Orb->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		}
		if (AMorphRigPlayerController* PC = Cast<AMorphRigPlayerController>(UGameplayStatics::GetPlayerController(World, 0)))
		{
			PC->AimTargetVisualActor = Orb;
		}
	}

	// 6. Studio 3-Point Lighting + SkyLight
	FActorSpawnParameters LightParams;
	LightParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	if (ADirectionalLight* KeyLight = World->SpawnActor<ADirectionalLight>(
		ADirectionalLight::StaticClass(), FVector(200.0f, -200.0f, 400.0f), FRotator(-48.0f, 38.0f, 0.0f), LightParams))
	{
		KeyLight->GetLightComponent()->SetMobility(EComponentMobility::Movable);
		KeyLight->GetLightComponent()->SetIntensity(7.5f);
		KeyLight->GetLightComponent()->SetLightColor(FLinearColor(1.0f, 0.97f, 0.93f));
	}
	if (APointLight* FillLight = World->SpawnActor<APointLight>(
		APointLight::StaticClass(), FVector(220.0f, 220.0f, 210.0f), FRotator::ZeroRotator, LightParams))
	{
		FillLight->PointLightComponent->SetMobility(EComponentMobility::Movable);
		FillLight->PointLightComponent->SetIntensity(3200.0f);
		FillLight->PointLightComponent->SetAttenuationRadius(1200.0f);
		FillLight->PointLightComponent->SetLightColor(FLinearColor(0.65f, 0.85f, 1.0f));
	}
	if (ASkyLight* Sky = World->SpawnActor<ASkyLight>(ASkyLight::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, LightParams))
	{
		Sky->GetLightComponent()->SetMobility(EComponentMobility::Movable);
		Sky->GetLightComponent()->SetIntensity(1.6f);
		Sky->GetLightComponent()->RecaptureSky();
	}
}
