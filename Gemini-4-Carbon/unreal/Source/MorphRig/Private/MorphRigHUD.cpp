#include "MorphRigHUD.h"
#include "MorphRigGameMode.h"
#include "MorphRigCharacter.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigGeneratedMeta.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"

AMorphRigHUD::AMorphRigHUD()
{
}

void AMorphRigHUD::BeginPlay()
{
	Super::BeginPlay();
}

void AMorphRigHUD::DrawFilledBox(float X, float Y, float W, float H, const FLinearColor& Color)
{
	DrawRect(Color, X, Y, W, H);
}

void AMorphRigHUD::DrawButton(float X, float Y, float W, float H, const FString& Label, FName HitName, bool bActive, const FLinearColor& Accent)
{
	const FLinearColor Bg = bActive ? (Accent * 0.65f + FLinearColor(0.05f, 0.08f, 0.12f, 0.92f)) : FLinearColor(0.09f, 0.12f, 0.16f, 0.88f);
	const FLinearColor Border = bActive ? Accent : FLinearColor(0.24f, 0.30f, 0.38f, 0.95f);
	DrawRect(Border, X, Y, W, H);
	DrawRect(Bg, X + 1.5f, Y + 1.5f, W - 3.0f, H - 3.0f);
	DrawText(Label, bActive ? FLinearColor::White : FLinearColor(0.86f, 0.90f, 0.95f), X + 7.0f, Y + 5.0f, GEngine->GetSmallFont(), 0.95f);
	AddHitBox(FVector2D(X, Y), FVector2D(W, H), HitName, true, 5);
}

void AMorphRigHUD::AppendSearchChar(TCHAR Ch)
{
	if (BrowserSearchFilter.Len() < 24)
	{
		BrowserSearchFilter.AppendChar(Ch);
		BrowserScrollOffset = 0;
	}
}

void AMorphRigHUD::BackspaceSearch()
{
	if (BrowserSearchFilter.Len() > 0)
	{
		BrowserSearchFilter.LeftChopInline(1);
		BrowserScrollOffset = 0;
	}
}

void AMorphRigHUD::ClearSearch()
{
	BrowserSearchFilter.Empty();
	BrowserScrollOffset = 0;
}

void AMorphRigHUD::ScrollBrowser(int32 DeltaRows)
{
	BrowserScrollOffset = FMath::Max(0, BrowserScrollOffset + DeltaRows);
}

void AMorphRigHUD::PollKeyboardShortcuts()
{
	APlayerController* PC = GetOwningPlayerController();
	AMorphRigGameMode* GM = GetWorld() ? Cast<AMorphRigGameMode>(GetWorld()->GetAuthGameMode()) : nullptr;
	AMorphRigCharacter* Op = GM ? GM->PrimaryOperative.Get() : nullptr;
	UMorphRigAnimInstance* Anim = Op ? Op->GetMorphRigAnim() : nullptr;
	if (!PC || !GM || !Op || !Anim)
	{
		return;
	}

	auto WasJustPressed = [&](const FKey& Key) -> bool
	{
		const bool bDown = PC->IsInputKeyDown(Key);
		const bool bPrev = PrevKeyStates.FindRef(Key);
		PrevKeyStates.Add(Key, bDown);
		return bDown && !bPrev;
	};

	// Mouse wheel zoom or browser scroll
	if (PC->WasInputKeyJustPressed(EKeys::MouseScrollUp))
	{
		if (ActiveTab == EMorphRigHUDTab::ClipBrowser96) { ScrollBrowser(-3); }
		else { GM->OrbitDistance = FMath::Clamp(GM->OrbitDistance - 28.0f, 58.0f, 1600.0f); }
	}
	if (PC->WasInputKeyJustPressed(EKeys::MouseScrollDown))
	{
		if (ActiveTab == EMorphRigHUDTab::ClipBrowser96) { ScrollBrowser(+3); }
		else { GM->OrbitDistance = FMath::Clamp(GM->OrbitDistance + 28.0f, 58.0f, 1600.0f); }
	}

	// If typing into the 96-Clip Search Box, capture alphanumeric + underscore + backspace!
	if (bSearchBoxFocused && ActiveTab == EMorphRigHUDTab::ClipBrowser96)
	{
		if (WasJustPressed(EKeys::BackSpace)) { BackspaceSearch(); }
		if (WasJustPressed(EKeys::Escape) || WasJustPressed(EKeys::Enter)) { bSearchBoxFocused = false; }
		static const FKey AlphaKeys[] = {
			EKeys::A, EKeys::B, EKeys::C, EKeys::D, EKeys::E, EKeys::F, EKeys::G, EKeys::H, EKeys::I,
			EKeys::J, EKeys::K, EKeys::L, EKeys::M, EKeys::N, EKeys::O, EKeys::P, EKeys::Q, EKeys::R,
			EKeys::S, EKeys::T, EKeys::U, EKeys::V, EKeys::W, EKeys::X, EKeys::Y, EKeys::Z,
			EKeys::Zero, EKeys::One, EKeys::Two, EKeys::Three, EKeys::Eight, EKeys::Nine, EKeys::Hyphen
		};
		for (const FKey& K : AlphaKeys)
		{
			if (WasJustPressed(K))
			{
				const FString KS = K.GetFName().ToString().ToLower();
				if (KS == TEXT("hyphen")) { AppendSearchChar(TEXT('_')); }
				else if (KS == TEXT("zero")) { AppendSearchChar(TEXT('0')); }
				else if (KS == TEXT("one")) { AppendSearchChar(TEXT('1')); }
				else if (KS == TEXT("two")) { AppendSearchChar(TEXT('2')); }
				else if (KS == TEXT("three")) { AppendSearchChar(TEXT('3')); }
				else if (KS == TEXT("eight")) { AppendSearchChar(TEXT('8')); }
				else if (KS == TEXT("nine")) { AppendSearchChar(TEXT('9')); }
				else if (KS.Len() == 1) { AppendSearchChar(KS[0]); }
			}
		}
		return;
	}

	// Continuous WASD 8-direction locomotion & Q/E independent character facing yaw!
	const float Dt = GetWorld()->GetDeltaSeconds();
	if (!GM->bShowcaseRunning && GM->CaptureMode.IsEmpty() && !GM->bPerfBenchmarkMode)
	{
		float Fwd = 0.0f, Right = 0.0f;
		if (PC->IsInputKeyDown(EKeys::W)) { Fwd += 1.0f; }
		if (PC->IsInputKeyDown(EKeys::S)) { Fwd -= 1.0f; }
		if (PC->IsInputKeyDown(EKeys::D)) { Right += 1.0f; }
		if (PC->IsInputKeyDown(EKeys::A)) { Right -= 1.0f; }
		Op->DesiredMoveInput = FVector2D(Fwd, Right);

		if (PC->IsInputKeyDown(EKeys::LeftShift)) { Op->SpeedTier = 2; }
		else if (PC->IsInputKeyDown(EKeys::LeftControl)) { Op->SpeedTier = 0; }

		if (PC->IsInputKeyDown(EKeys::Q)) { Op->DesiredFacingYaw -= 110.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::E)) { Op->DesiredFacingYaw += 110.0f * Dt; }

		// IJKL / UO moves the 3D Aim Target Orb smoothly
		FVector AimDelta = FVector::ZeroVector;
		if (PC->IsInputKeyDown(EKeys::I)) { AimDelta.Z += 180.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::K)) { AimDelta.Z -= 180.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::J)) { AimDelta.Y -= 220.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::L)) { AimDelta.Y += 220.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::U)) { AimDelta.X += 220.0f * Dt; }
		if (PC->IsInputKeyDown(EKeys::O)) { AimDelta.X -= 220.0f * Dt; }
		if (!AimDelta.IsNearlyZero()) { GM->MoveAimTarget(AimDelta); }
	}

	// Camera presets 1..8
	if (WasJustPressed(EKeys::One))   { GM->SetCameraPreset(EMorphRigCameraPreset::OrbitClose); }
	if (WasJustPressed(EKeys::Two))   { GM->SetCameraPreset(EMorphRigCameraPreset::FullBodyFront); }
	if (WasJustPressed(EKeys::Three)) { GM->SetCameraPreset(EMorphRigCameraPreset::FullBodySide); }
	if (WasJustPressed(EKeys::Four))  { GM->SetCameraPreset(EMorphRigCameraPreset::TopDownMOBA); }
	if (WasJustPressed(EKeys::Five))  { GM->SetCameraPreset(EMorphRigCameraPreset::TopDown120Px); }
	if (WasJustPressed(EKeys::Six))   { GM->SetCameraPreset(EMorphRigCameraPreset::FacialCloseUp); }
	if (WasJustPressed(EKeys::Seven)) { GM->SetCameraPreset(EMorphRigCameraPreset::RampStepsIK); }
	if (WasJustPressed(EKeys::Eight)) { GM->SetCameraPreset(EMorphRigCameraPreset::PropStation); }

	// Action hotkeys
	if (WasJustPressed(EKeys::SpaceBar)) { Op->Jump(); Anim->TriggerJump(); }
	if (WasJustPressed(EKeys::F))        { Anim->TriggerMeleeAttack(); }
	if (WasJustPressed(EKeys::G))        { Anim->TriggerUpperBodyAction(EMorphRigUpperBodyMode::RangedBurst); }
	if (WasJustPressed(EKeys::R))        { Anim->TriggerReload(); }
	if (WasJustPressed(EKeys::C))        { if (Anim->PrimaryState == EMorphRigPrimaryState::ChannelLoop || Anim->PrimaryState == EMorphRigPrimaryState::ChannelStart) Anim->InterruptChannel(); else Anim->StartChannel(0.0f); }
	if (WasJustPressed(EKeys::V))        { Op->TriggerDialoguePerformance(); }
	if (WasJustPressed(EKeys::B))        { Anim->TriggerBlink(); }
	if (WasJustPressed(EKeys::Z))        { Anim->TriggerDash(TEXT("f")); }
	if (WasJustPressed(EKeys::X))        { if (Anim->IsTerminalDead()) Anim->TriggerRespawn(); else Anim->TriggerDeath(true); }
	if (WasJustPressed(EKeys::T))        { Op->SetTeamVariant(1 - Op->TeamIndex, Op->bShowSecondaryTeamCue); }
	if (WasJustPressed(EKeys::H))        { bShowHUDPanels = !bShowHUDPanels; }
	if (WasJustPressed(EKeys::BackSpace)){ Op->ResetOperativeFull(FVector(0.0f, 0.0f, 90.0f), 0.0f); }
}

void AMorphRigHUD::RenderOffscreenTelemetry(UCanvas* TargetCanvas)
{
	if (!TargetCanvas || !bShowHUDPanels)
	{
		return;
	}
	UCanvas* PrevCanvas = Canvas;
	Canvas = TargetCanvas;
	bDrawingOffscreen = true;
	DrawHUD();
	bDrawingOffscreen = false;
	Canvas = PrevCanvas;
}

void AMorphRigHUD::DrawHUD()
{
	if (!bDrawingOffscreen)
	{
		Super::DrawHUD();
		PollKeyboardShortcuts();
	}

	if (!Canvas || !GEngine) { return; }
	AMorphRigGameMode* GM = GetWorld() ? Cast<AMorphRigGameMode>(GetWorld()->GetAuthGameMode()) : nullptr;
	AMorphRigCharacter* Op = GM ? GM->PrimaryOperative.Get() : nullptr;
	UMorphRigAnimInstance* Anim = Op ? Op->GetMorphRigAnim() : nullptr;
	if (!GM || !Op || !Anim) { return; }

	// In turntable capture mode we keep the frame 100% clean full-body studio
	if (!bShowHUDPanels && !GM->CaptureMode.IsEmpty())
	{
		return;
	}

	// Compact Top Telemetry Ribbon (shown in interactive mode and motion/face showcase)
	DrawFilledBox(16.0f, 14.0f, Canvas->ClipX - 32.0f, 54.0f, FLinearColor(0.04f, 0.06f, 0.09f, 0.86f));
	const FString TopLine1 = FString::Printf(
		TEXT("MORPHRIG OPERATIVE SHOWCASE  |  FPS: %.1f (%.2f ms)  |  Instances: %d  |  Team: %s  |  LOD: %d (%s)  |  Aim(Y:%.0f, P:%.0f)"),
		GM->SmoothedFPS, GM->SmoothedFrameMs,
		GM->bTenOperativesActive ? 10 : 1,
		(Op->TeamIndex == 0) ? TEXT("A [Cyan/Diamond]") : TEXT("B [Crimson/Chevron]"),
		Op->GetCurrentDisplayedLOD(),
		(Op->ForcedLODSelection < 0) ? TEXT("Auto") : TEXT("Forced"),
		Anim->AimYawDeg, Anim->AimPitchDeg);
	DrawText(TopLine1, FLinearColor(0.0f, 0.90f, 1.0f), 28.0f, 20.0f, GEngine->GetSmallFont(), 1.05f);
	DrawText(Anim->GetReadableStateSummary(), FLinearColor(0.92f, 0.95f, 0.98f), 28.0f, 42.0f, GEngine->GetSmallFont(), 1.0f);

	// During video capture of motion/face, show ONLY the clean top telemetry bar + bottom-right live marker log so character is unobstructed!
	if (!GM->CaptureMode.IsEmpty() || !bShowHUDPanels)
	{
		if (Anim->RecentEvents.Num() > 0)
		{
			const float LogW = 430.0f, LogX = Canvas->ClipX - LogW - 18.0f, LogY = Canvas->ClipY - 148.0f;
			DrawFilledBox(LogX, LogY, LogW, 132.0f, FLinearColor(0.04f, 0.06f, 0.09f, 0.80f));
			DrawText(TEXT("DEDUPLICATED EVENT MARKERS:"), FLinearColor(0.0f, 0.85f, 1.0f), LogX + 10.0f, LogY + 6.0f, GEngine->GetSmallFont(), 0.95f);
			for (int32 i = 0; i < FMath::Min(5, Anim->RecentEvents.Num()); ++i)
			{
				const FMorphRigEventRecord& E = Anim->RecentEvents[i];
				const FString EStr = FString::Printf(TEXT("[%.2fs] %s :: %s"), E.WorldTimeSec, *E.ClipId.ToString(), *E.MarkerName.ToString());
				DrawText(EStr, FLinearColor(0.88f, 0.92f, 0.96f), LogX + 10.0f, LogY + 26.0f + i * 19.0f, GEngine->GetSmallFont(), 0.92f);
			}
		}
		return;
	}

	// =========================================================================
	// INTERACTIVE LEFT CONTROL PANEL (Tabs: States | 96-Clip Browser | Face Rig | Help)
	// =========================================================================
	const float PX = 16.0f, PY = 78.0f, PW = 430.0f, PH = Canvas->ClipY - 96.0f;
	DrawFilledBox(PX, PY, PW, PH, FLinearColor(0.04f, 0.055f, 0.08f, 0.88f));

	DrawButton(PX + 8.0f,   PY + 8.0f, 100.0f, 26.0f, TEXT("States & IK"),  TEXT("TAB_0"), ActiveTab == EMorphRigHUDTab::ActionsAndStates);
	DrawButton(PX + 112.0f, PY + 8.0f, 106.0f, 26.0f, TEXT("96 Clips"),     TEXT("TAB_1"), ActiveTab == EMorphRigHUDTab::ClipBrowser96);
	DrawButton(PX + 222.0f, PY + 8.0f, 100.0f, 26.0f, TEXT("Face & Lip"),   TEXT("TAB_2"), ActiveTab == EMorphRigHUDTab::FaceAndVisemes);
	DrawButton(PX + 326.0f, PY + 8.0f, 96.0f,  26.0f, TEXT("Help [H]"),     TEXT("TAB_3"), ActiveTab == EMorphRigHUDTab::ControlsHelp);

	float CY = PY + 44.0f;

	if (ActiveTab == EMorphRigHUDTab::ActionsAndStates)
	{
		DrawText(TEXT("CAMERA & PRESENTATION:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("1: Orbit"),   TEXT("CAM_0"), GM->ActiveCameraPreset == EMorphRigCameraPreset::OrbitClose);
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("2: Front"),   TEXT("CAM_1"), GM->ActiveCameraPreset == EMorphRigCameraPreset::FullBodyFront);
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("3: Side"),    TEXT("CAM_2"), GM->ActiveCameraPreset == EMorphRigCameraPreset::FullBodySide);
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("4: MOBA 52d"),TEXT("CAM_3"), GM->ActiveCameraPreset == EMorphRigCameraPreset::TopDownMOBA);
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("5: 120px"),   TEXT("CAM_4"), GM->ActiveCameraPreset == EMorphRigCameraPreset::TopDown120Px);
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("6: Face"),    TEXT("CAM_5"), GM->ActiveCameraPreset == EMorphRigCameraPreset::FacialCloseUp);
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("7: Ramp/IK"), TEXT("CAM_6"), GM->ActiveCameraPreset == EMorphRigCameraPreset::RampStepsIK);
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("8: Wide"),    TEXT("CAM_7"), GM->ActiveCameraPreset == EMorphRigCameraPreset::PropStation);
		CY += 32.0f;

		DrawText(TEXT("TEAM, LOD, SKELETON, INSTANCES & RATE:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		DrawButton(PX + 10.0f,  CY, 132.0f, 24.0f, TEXT("Team A/B [T]"), TEXT("TOG_TEAM"), Op->TeamIndex == 1, FLinearColor(1.0f, 0.35f, 0.1f));
		DrawButton(PX + 146.0f, CY, 132.0f, 24.0f, TEXT("Team Icon Cue"),TEXT("TOG_CUE"),  Op->bShowSecondaryTeamCue);
		DrawButton(PX + 282.0f, CY, 136.0f, 24.0f, GM->bTenOperativesActive ? TEXT("10 Operatives") : TEXT("1 Operative"), TEXT("TOG_10X"), GM->bTenOperativesActive);
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 76.0f, 24.0f, TEXT("LOD Auto"), TEXT("LOD_AUTO"), Op->ForcedLODSelection == -1);
		DrawButton(PX + 90.0f,  CY, 68.0f, 24.0f, TEXT("LOD 0"),    TEXT("LOD_0"),    Op->ForcedLODSelection == 0);
		DrawButton(PX + 162.0f, CY, 68.0f, 24.0f, TEXT("LOD 1"),    TEXT("LOD_1"),    Op->ForcedLODSelection == 1);
		DrawButton(PX + 234.0f, CY, 68.0f, 24.0f, TEXT("LOD 2"),    TEXT("LOD_2"),    Op->ForcedLODSelection == 2);
		DrawButton(PX + 306.0f, CY, 112.0f,24.0f, TEXT("Skel Overlay"), TEXT("TOG_SKEL"), Op->bShowSkeletonOverlay);
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("Rate 0.5x"), TEXT("RATE_05"), FMath::IsNearlyEqual(Anim->ActionPlayRate, 0.5f, 0.05f));
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("Rate 1.0x"), TEXT("RATE_10"), FMath::IsNearlyEqual(Anim->ActionPlayRate, 1.0f, 0.05f));
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Rate 1.5x"), TEXT("RATE_15"), FMath::IsNearlyEqual(Anim->ActionPlayRate, 1.5f, 0.05f));
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Ground IK"), TEXT("TOG_IK"),  Anim->bEnableGroundIK);
		CY += 32.0f;

		DrawText(TEXT("LOCOMOTION, MOBILITY & PROP ACTIONS:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("Walk 150"),  TEXT("SPD_0"), Op->SpeedTier == 0);
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("Run 400"),   TEXT("SPD_1"), Op->SpeedTier == 1);
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Sprint 650"),TEXT("SPD_2"), Op->SpeedTier == 2);
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Jump [Spc]"),TEXT("ACT_JUMP"));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 76.0f, 24.0f, TEXT("Dash F"), TEXT("DASH_F"));
		DrawButton(PX + 90.0f,  CY, 76.0f, 24.0f, TEXT("Dash B"), TEXT("DASH_B"));
		DrawButton(PX + 170.0f, CY, 76.0f, 24.0f, TEXT("Dash L"), TEXT("DASH_L"));
		DrawButton(PX + 250.0f, CY, 76.0f, 24.0f, TEXT("Dash R"), TEXT("DASH_R"));
		DrawButton(PX + 330.0f, CY, 88.0f, 24.0f, TEXT("Blink [B]"), TEXT("ACT_BLINK"));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("Melee 1-2-3"),TEXT("ACT_MELEE"));
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("Fire Shot"),  TEXT("ACT_FIRE"));
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Burst x3"),   TEXT("ACT_BURST"));
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Reload [R]"), TEXT("ACT_RELOAD"));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("Cast Dir"),   TEXT("ACT_CASTD"));
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("Cast Grnd"),  TEXT("ACT_CASTG"));
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Cast Self"),  TEXT("ACT_CASTS"));
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Deploy Prop"),TEXT("ACT_DEPLOY"));
		CY += 32.0f;

		DrawText(TEXT("SUSTAINED & ARBITRARY INTERRUPTS (NO SNAP!):"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		DrawButton(PX + 10.0f,  CY, 132.0f, 24.0f, TEXT("Channel Start"), TEXT("CH_START"), Anim->PrimaryState == EMorphRigPrimaryState::ChannelLoop);
		DrawButton(PX + 146.0f, CY, 132.0f, 24.0f, TEXT("Channel End"),   TEXT("CH_END"));
		DrawButton(PX + 282.0f, CY, 136.0f, 24.0f, TEXT("Interrupt [C]"), TEXT("CH_INT"), false, FLinearColor(1.0f, 0.35f, 0.1f));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 132.0f, 24.0f, TEXT("Charge Start"),  TEXT("CG_START"), Anim->PrimaryState == EMorphRigPrimaryState::ChargeHold);
		DrawButton(PX + 146.0f, CY, 132.0f, 24.0f, TEXT("Charge Rel"),    TEXT("CG_REL"));
		DrawButton(PX + 282.0f, CY, 136.0f, 24.0f, TEXT("Charge Cancel"), TEXT("CG_CAN"));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 132.0f, 24.0f, TEXT("Uplink Start"),  TEXT("UP_START"), Anim->PrimaryState == EMorphRigPrimaryState::UplinkLoop);
		DrawButton(PX + 146.0f, CY, 132.0f, 24.0f, TEXT("Uplink End"),    TEXT("UP_END"));
		DrawButton(PX + 282.0f, CY, 136.0f, 24.0f, TEXT("Uplink Cancel"), TEXT("UP_CAN"));
		CY += 32.0f;

		DrawText(TEXT("HITS, DISABLES, CC, DEATH/RESPAWN & SPEECH:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		DrawButton(PX + 10.0f,  CY, 68.0f, 24.0f, TEXT("Hit F"), TEXT("HIT_F"));
		DrawButton(PX + 82.0f,  CY, 68.0f, 24.0f, TEXT("Hit B"), TEXT("HIT_B"));
		DrawButton(PX + 154.0f, CY, 68.0f, 24.0f, TEXT("Hit L"), TEXT("HIT_L"));
		DrawButton(PX + 226.0f, CY, 68.0f, 24.0f, TEXT("Hit R"), TEXT("HIT_R"));
		DrawButton(PX + 298.0f, CY, 120.0f,24.0f, TEXT("Wounded Idle"), TEXT("CC_WOUND"), Anim->bWounded);
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("Stun"),       TEXT("DIS_STUN"));
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("Sleep"),      TEXT("DIS_SLEEP"));
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Knockback"),  TEXT("DIS_KB"));
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Knockup"),    TEXT("DIS_KU"));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 98.0f, 24.0f, TEXT("KD Front"),   TEXT("DIS_KDF"));
		DrawButton(PX + 112.0f, CY, 98.0f, 24.0f, TEXT("KD Back"),    TEXT("DIS_KDB"));
		DrawButton(PX + 214.0f, CY, 98.0f, 24.0f, TEXT("Death Frnt"), TEXT("DIE_F"), false, FLinearColor(0.95f, 0.2f, 0.2f));
		DrawButton(PX + 316.0f, CY, 102.0f,24.0f, TEXT("Death Back"), TEXT("DIE_B"), false, FLinearColor(0.95f, 0.2f, 0.2f));
		CY += 28.0f;
		DrawButton(PX + 10.0f,  CY, 76.0f, 24.0f, TEXT("Root"),    TEXT("CC_ROOT"),  Anim->bRooted);
		DrawButton(PX + 90.0f,  CY, 76.0f, 24.0f, TEXT("Silence"), TEXT("CC_SIL"),   Anim->bSilenced);
		DrawButton(PX + 170.0f, CY, 76.0f, 24.0f, TEXT("Disarm"),  TEXT("CC_DIS"),   Anim->bDisarmed);
		DrawButton(PX + 250.0f, CY, 76.0f, 24.0f, TEXT("Fear"),    TEXT("CC_FEAR"),  Anim->bFeared);
		DrawButton(PX + 330.0f, CY, 88.0f, 24.0f, TEXT("Stasis"),  TEXT("CC_STASIS"),Anim->bStasis);
		CY += 30.0f;

		DrawButton(PX + 10.0f,  CY, 132.0f, 26.0f, TEXT("Respawn [X]"),       TEXT("ACT_RESPAWN"), false, FLinearColor(0.1f, 0.9f, 0.5f));
		DrawButton(PX + 146.0f, CY, 132.0f, 26.0f, TEXT("Dialogue [V]"),      TEXT("ACT_DIALOGUE"), Anim->PrimaryClip == TEXT("dialogue"));
		DrawButton(PX + 282.0f, CY, 136.0f, 26.0f, TEXT("Reset [Bksp]"),      TEXT("ACT_RESET"));
		CY += 30.0f;
		DrawButton(PX + 10.0f,  CY, 408.0f, 26.0f, GM->bShowcaseRunning ? TEXT("Stop Deterministic Showcase") : TEXT("Run Deterministic Showcase Sequence (Logs Trace)"), TEXT("ACT_SHOWCASE"), GM->bShowcaseRunning);
	}
	else if (ActiveTab == EMorphRigHUDTab::ClipBrowser96)
	{
		// Searchable 96-Clip Animation Browser!
		const FString SearchText = FString::Printf(TEXT("Search Filter: [%s%s]"), *BrowserSearchFilter, bSearchBoxFocused ? TEXT("|") : TEXT(" (Click to Type)"));
		DrawButton(PX + 10.0f, CY, 290.0f, 26.0f, SearchText, TEXT("BRW_SEARCH"), bSearchBoxFocused);
		DrawButton(PX + 304.0f, CY, 54.0f, 26.0f, TEXT("Clear"), TEXT("BRW_CLR"));
		DrawButton(PX + 362.0f, CY, 56.0f, 26.0f, TEXT("Exit"),  TEXT("BRW_EXIT"));
		CY += 32.0f;

		DrawButton(PX + 10.0f,  CY, 198.0f, 22.0f, TEXT("^ Scroll Up (Wheel)"),   TEXT("BRW_UP"));
		DrawButton(PX + 216.0f, CY, 202.0f, 22.0f, TEXT("v Scroll Down (Wheel)"), TEXT("BRW_DN"));
		CY += 26.0f;

		TArray<int32> Filtered;
		for (int32 i = 0; i < GMorphRigClipCount; ++i)
		{
			const FString IdStr(GMorphRigClips[i].ClipId);
			if (BrowserSearchFilter.IsEmpty() || IdStr.Contains(BrowserSearchFilter, ESearchCase::IgnoreCase))
			{
				Filtered.Add(i);
			}
		}

		const int32 MaxRows = FMath::Max(6, FMath::FloorToInt((PH - 125.0f) / 24.0f));
		const int32 StartIdx = FMath::Clamp(BrowserScrollOffset, 0, FMath::Max(0, Filtered.Num() - MaxRows));
		for (int32 r = 0; r < MaxRows && (StartIdx + r) < Filtered.Num(); ++r)
		{
			const int32 ClipIdx = Filtered[StartIdx + r];
			const FMorphRigClipMeta& M = GMorphRigClips[ClipIdx];
			const FString RowLabel = FString::Printf(TEXT("%02d. %-19s [%s | %.2fs]"), ClipIdx + 1, M.ClipId, M.Form, M.DurationSec);
			const FName HitId(*FString::Printf(TEXT("PLAYCLIP_%d"), ClipIdx));
			const bool bPlaying = (Anim->PrimaryClip == FName(M.ClipId));
			DrawButton(PX + 10.0f, CY, 408.0f, 22.0f, RowLabel, HitId, bPlaying);
			CY += 24.0f;
		}
	}
	else if (ActiveTab == EMorphRigHUDTab::FaceAndVisemes)
	{
		DrawButton(PX + 10.0f,  CY, 198.0f, 26.0f, Anim->FaceManual.bEnableManualOverride ? TEXT("Manual Face: ON") : TEXT("Manual Face: OFF"), TEXT("FACE_TOG"), Anim->FaceManual.bEnableManualOverride);
		DrawButton(PX + 216.0f, CY, 100.0f, 26.0f, TEXT("Face Cam [6]"), TEXT("CAM_5"), GM->ActiveCameraPreset == EMorphRigCameraPreset::FacialCloseUp);
		DrawButton(PX + 320.0f, CY, 98.0f,  26.0f, TEXT("Reset Face"),   TEXT("FACE_RST"));
		CY += 32.0f;

		DrawText(TEXT("ASYMMETRIC LEFT / RIGHT CONTROLS (Click Cycles 0 / 0.5 / 1):"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		auto DrawLRRow = [&](const TCHAR* NameL, float ValL, FName HitL, const TCHAR* NameR, float ValR, FName HitR)
		{
			DrawButton(PX + 10.0f,  CY, 200.0f, 23.0f, FString::Printf(TEXT("%s: %.2f"), NameL, ValL), HitL, ValL > 0.05f);
			DrawButton(PX + 218.0f, CY, 200.0f, 23.0f, FString::Printf(TEXT("%s: %.2f"), NameR, ValR), HitR, ValR > 0.05f);
			CY += 25.0f;
		};
		const FMorphRigFaceManualState& FM = Anim->FaceManual;
		DrawLRRow(TEXT("Blink L"),    FM.BlinkL,    TEXT("FC_BL_L"), TEXT("Blink R"),    FM.BlinkR,    TEXT("FC_BL_R"));
		DrawLRRow(TEXT("Squint L"),   FM.SquintL,   TEXT("FC_SQ_L"), TEXT("Squint R"),   FM.SquintR,   TEXT("FC_SQ_R"));
		DrawLRRow(TEXT("BrowUp L"),   FM.BrowUpL,   TEXT("FC_BU_L"), TEXT("BrowUp R"),   FM.BrowUpR,   TEXT("FC_BU_R"));
		DrawLRRow(TEXT("BrowDn L"),   FM.BrowDownL, TEXT("FC_BD_L"), TEXT("BrowDn R"),   FM.BrowDownR, TEXT("FC_BD_R"));
		DrawLRRow(TEXT("Smile L"),    FM.SmileL,    TEXT("FC_SM_L"), TEXT("Smile R"),    FM.SmileR,    TEXT("FC_SM_R"));
		DrawLRRow(TEXT("Frown L"),    FM.FrownL,    TEXT("FC_FR_L"), TEXT("Frown R"),    FM.FrownR,    TEXT("FC_FR_R"));
		DrawLRRow(TEXT("Jaw Open"),   FM.JawOpen,   TEXT("FC_JAW"),  TEXT("Lip Close"),  FM.LipClose,  TEXT("FC_LIP"));
		DrawLRRow(TEXT("Pucker"),     FM.MouthPucker,TEXT("FC_PUK"), TEXT("Tongue Out"), FM.TongueOut, TEXT("FC_TNG"));
		DrawLRRow(TEXT("Eye Yaw"),    FM.EyeYawDeg, TEXT("FC_EYAW"), TEXT("Eye Pitch"),  FM.EyePitchDeg,TEXT("FC_EPIT"));
		CY += 6.0f;

		DrawText(TEXT("6 EXPRESSION PRESETS:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		static const TCHAR* Presets[6] = {
			TEXT("expr_joy_confidence"), TEXT("expr_anger"), TEXT("expr_concern_sadness"),
			TEXT("expr_surprise"), TEXT("expr_pain"), TEXT("expr_focus")
		};
		static const TCHAR* PresetShort[6] = { TEXT("Joy/Conf"), TEXT("Anger"), TEXT("Concern"), TEXT("Surprise"), TEXT("Pain"), TEXT("Focus") };
		for (int32 p = 0; p < 6; ++p)
		{
			const float BX = PX + 10.0f + (p % 3) * 138.0f;
			const float BY = CY + (p / 3) * 26.0f;
			DrawButton(BX, BY, 132.0f, 23.0f, PresetShort[p], FName(*FString::Printf(TEXT("PRE_%d"), p)), FM.ActivePreset == FName(Presets[p]));
		}
		CY += 58.0f;

		DrawText(TEXT("13 SPEECH VISEMES + SPOKEN DIALOGUE:"), FLinearColor(0.6f, 0.8f, 1.0f), PX + 10.0f, CY, GEngine->GetSmallFont()); CY += 18.0f;
		static const TCHAR* Visemes[13] = {
			TEXT("V_SIL"), TEXT("V_MBP"), TEXT("V_FV"), TEXT("V_TH"), TEXT("V_TDNL"),
			TEXT("V_SZ"), TEXT("V_KG"), TEXT("V_AA"), TEXT("V_EE"), TEXT("V_EH"),
			TEXT("V_OH"), TEXT("V_OU"), TEXT("V_ER")
		};
		for (int32 v = 0; v < 13; ++v)
		{
			const float BX = PX + 10.0f + (v % 5) * 82.0f;
			const float BY = CY + (v / 5) * 25.0f;
			DrawButton(BX, BY, 78.0f, 22.0f, Visemes[v], FName(*FString::Printf(TEXT("VIS_%d"), v)), FM.ActiveViseme == FName(Visemes[v]));
		}
		CY += 80.0f;
		DrawButton(PX + 10.0f, CY, 408.0f, 26.0f, TEXT("Play 16.5s Synchronized Dialogue Performance [V]"), TEXT("ACT_DIALOGUE"));
	}
	else // ControlsHelp
	{
		static const TCHAR* HelpLines[] = {
			TEXT("KEYBOARD & MOUSE CONTROLS:"),
			TEXT("  W / A / S / D     : 8-Direction Travel (Independent of Facing!)"),
			TEXT("  Left Ctrl / Shift : Walk (150 cm/s) / Sprint (650 cm/s)"),
			TEXT("  Q / E             : Rotate Character Facing Yaw Left / Right"),
			TEXT("  I / J / K / L / U / O : Move 3D Aim Target Orb in Room"),
			TEXT("  Right-Mouse Drag  : Orbit Inspection Camera"),
			TEXT("  Mouse Wheel       : Zoom Camera (or Scroll 96-Clip Browser)"),
			TEXT("  1 .. 8            : Camera Presets (Orbit/Front/Side/MOBA/120px/Face/IK)"),
			TEXT("  Spacebar          : Jump -> Airborne -> Soft/Heavy Landing"),
			TEXT("  F                 : Melee 1 -> 2 -> 3 Forearm-Blade Combo"),
			TEXT("  G                 : Layered Moving Ranged 3-Shot Burst"),
			TEXT("  R                 : Physical Wrist-Emitter Cell Reload"),
			TEXT("  C                 : Start Beam Channel / Interrupt Midway (No Snap!)"),
			TEXT("  Z / B             : 2m Root-Motion Dash / Event Blink Teleport"),
			TEXT("  V                 : Play Synchronized Spoken Dialogue + Audio"),
			TEXT("  X                 : Trigger Priority Death / Respawn"),
			TEXT("  T                 : Switch Team A (Cyan) <-> Team B (Crimson)"),
			TEXT("  Backspace         : Full Operative & Pose Reset"),
			TEXT("  H                 : Hide / Show Interactive HUD Panels")
		};
		for (const TCHAR* Line : HelpLines)
		{
			DrawText(Line, FLinearColor(0.88f, 0.92f, 0.96f), PX + 12.0f, CY, GEngine->GetSmallFont(), 0.96f);
			CY += 22.0f;
		}
	}

	// Bottom-Right Live Deduplicated Event Marker Feed
	const float LogW = 430.0f, LogX = Canvas->ClipX - LogW - 18.0f, LogY = Canvas->ClipY - 195.0f;
	DrawFilledBox(LogX, LogY, LogW, 178.0f, FLinearColor(0.04f, 0.055f, 0.08f, 0.85f));
	DrawText(TEXT("LIVE DEDUPLICATED EVENT MARKERS:"), FLinearColor(0.0f, 0.85f, 1.0f), LogX + 10.0f, LogY + 8.0f, GEngine->GetSmallFont(), 0.96f);
	for (int32 i = 0; i < FMath::Min(7, Anim->RecentEvents.Num()); ++i)
	{
		const FMorphRigEventRecord& E = Anim->RecentEvents[i];
		const FString EStr = FString::Printf(TEXT("[t=%.2fs] %-15s -> %s (%.2fx)"),
			E.WorldTimeSec, *E.ClipId.ToString(), *E.MarkerName.ToString(), E.PlayRate);
		DrawText(EStr, FLinearColor(0.88f, 0.92f, 0.96f), LogX + 10.0f, LogY + 28.0f + i * 20.0f, GEngine->GetSmallFont(), 0.92f);
	}
}

void AMorphRigHUD::NotifyHitBoxClick(FName BoxName)
{
	Super::NotifyHitBoxClick(BoxName);

	AMorphRigGameMode* GM = GetWorld() ? Cast<AMorphRigGameMode>(GetWorld()->GetAuthGameMode()) : nullptr;
	AMorphRigCharacter* Op = GM ? GM->PrimaryOperative.Get() : nullptr;
	UMorphRigAnimInstance* Anim = Op ? Op->GetMorphRigAnim() : nullptr;
	if (!GM || !Op || !Anim) { return; }

	const FString S = BoxName.ToString();
	bSearchBoxFocused = (BoxName == TEXT("BRW_SEARCH"));

	if (BoxName == TEXT("TAB_0")) { ActiveTab = EMorphRigHUDTab::ActionsAndStates; return; }
	if (BoxName == TEXT("TAB_1")) { ActiveTab = EMorphRigHUDTab::ClipBrowser96; return; }
	if (BoxName == TEXT("TAB_2")) { ActiveTab = EMorphRigHUDTab::FaceAndVisemes; return; }
	if (BoxName == TEXT("TAB_3")) { ActiveTab = EMorphRigHUDTab::ControlsHelp; return; }

	if (S.StartsWith(TEXT("CAM_")))
	{
		const int32 Idx = FCString::Atoi(*S.RightChop(4));
		GM->SetCameraPreset(static_cast<EMorphRigCameraPreset>(FMath::Clamp(Idx, 0, 7)));
		return;
	}

	if (BoxName == TEXT("TOG_TEAM"))   { Op->SetTeamVariant(1 - Op->TeamIndex, Op->bShowSecondaryTeamCue); return; }
	if (BoxName == TEXT("TOG_CUE"))    { Op->SetTeamVariant(Op->TeamIndex, !Op->bShowSecondaryTeamCue); return; }
	if (BoxName == TEXT("TOG_10X"))    { GM->SetTenOperativesEnabled(!GM->bTenOperativesActive); return; }
	if (BoxName == TEXT("LOD_AUTO"))   { Op->SetForcedLODMode(-1); return; }
	if (BoxName == TEXT("LOD_0"))      { Op->SetForcedLODMode(0); return; }
	if (BoxName == TEXT("LOD_1"))      { Op->SetForcedLODMode(1); return; }
	if (BoxName == TEXT("LOD_2"))      { Op->SetForcedLODMode(2); return; }
	if (BoxName == TEXT("TOG_SKEL"))   { Op->bShowSkeletonOverlay = !Op->bShowSkeletonOverlay; return; }
	if (BoxName == TEXT("RATE_05"))    { Anim->ActionPlayRate = 0.5f; return; }
	if (BoxName == TEXT("RATE_10"))    { Anim->ActionPlayRate = 1.0f; return; }
	if (BoxName == TEXT("RATE_15"))    { Anim->ActionPlayRate = 1.5f; return; }
	if (BoxName == TEXT("TOG_IK"))     { Anim->bEnableGroundIK = !Anim->bEnableGroundIK; return; }

	if (BoxName == TEXT("SPD_0"))      { Op->SpeedTier = 0; return; }
	if (BoxName == TEXT("SPD_1"))      { Op->SpeedTier = 1; return; }
	if (BoxName == TEXT("SPD_2"))      { Op->SpeedTier = 2; return; }
	if (BoxName == TEXT("ACT_JUMP"))   { Op->Jump(); Anim->TriggerJump(); return; }
	if (BoxName == TEXT("DASH_F"))     { Anim->TriggerDash(TEXT("f")); return; }
	if (BoxName == TEXT("DASH_B"))     { Anim->TriggerDash(TEXT("b")); return; }
	if (BoxName == TEXT("DASH_L"))     { Anim->TriggerDash(TEXT("l")); return; }
	if (BoxName == TEXT("DASH_R"))     { Anim->TriggerDash(TEXT("r")); return; }
	if (BoxName == TEXT("ACT_BLINK"))  { Anim->TriggerBlink(); return; }

	if (BoxName == TEXT("ACT_MELEE"))  { Anim->TriggerMeleeAttack(); return; }
	if (BoxName == TEXT("ACT_FIRE"))   { Anim->TriggerUpperBodyAction(EMorphRigUpperBodyMode::RangedFire); return; }
	if (BoxName == TEXT("ACT_BURST"))  { Anim->TriggerUpperBodyAction(EMorphRigUpperBodyMode::RangedBurst); return; }
	if (BoxName == TEXT("ACT_RELOAD")) { Anim->TriggerReload(); return; }
	if (BoxName == TEXT("ACT_CASTD"))  { Anim->TriggerUpperBodyAction(EMorphRigUpperBodyMode::CastDirectional); return; }
	if (BoxName == TEXT("ACT_CASTG"))  { Anim->TriggerCastGround(); return; }
	if (BoxName == TEXT("ACT_CASTS"))  { Anim->TriggerCastSelf(); return; }
	if (BoxName == TEXT("ACT_DEPLOY")) { Anim->TriggerDeploy(); return; }

	if (BoxName == TEXT("CH_START"))   { Anim->StartChannel(0.0f); return; }
	if (BoxName == TEXT("CH_END"))     { Anim->FinishChannel(); return; }
	if (BoxName == TEXT("CH_INT"))     { Anim->InterruptChannel(); return; }
	if (BoxName == TEXT("CG_START"))   { Anim->StartCharge(); return; }
	if (BoxName == TEXT("CG_REL"))     { Anim->ReleaseCharge(); return; }
	if (BoxName == TEXT("CG_CAN"))     { Anim->CancelCharge(); return; }
	if (BoxName == TEXT("UP_START"))   { Anim->StartUplink(0.0f); return; }
	if (BoxName == TEXT("UP_END"))     { Anim->FinishUplink(); return; }
	if (BoxName == TEXT("UP_CAN"))     { Anim->CancelUplink(); return; }

	if (BoxName == TEXT("HIT_F"))      { Anim->TriggerAdditiveHit(TEXT("f")); return; }
	if (BoxName == TEXT("HIT_B"))      { Anim->TriggerAdditiveHit(TEXT("b")); return; }
	if (BoxName == TEXT("HIT_L"))      { Anim->TriggerAdditiveHit(TEXT("l")); return; }
	if (BoxName == TEXT("HIT_R"))      { Anim->TriggerAdditiveHit(TEXT("r")); return; }
	if (BoxName == TEXT("CC_WOUND"))   { Anim->bWounded = !Anim->bWounded; return; }
	if (BoxName == TEXT("DIS_STUN"))   { Anim->TriggerStun(1.4f); return; }
	if (BoxName == TEXT("DIS_SLEEP"))  { Anim->TriggerSleep(2.0f); return; }
	if (BoxName == TEXT("DIS_KB"))     { Anim->TriggerKnockback(); return; }
	if (BoxName == TEXT("DIS_KU"))     { Anim->TriggerKnockup(true); return; }
	if (BoxName == TEXT("DIS_KDF"))    { Anim->TriggerKnockdown(true, 1.2f); return; }
	if (BoxName == TEXT("DIS_KDB"))    { Anim->TriggerKnockdown(false, 1.2f); return; }
	if (BoxName == TEXT("DIE_F"))      { Anim->TriggerDeath(true); return; }
	if (BoxName == TEXT("DIE_B"))      { Anim->TriggerDeath(false); return; }

	if (BoxName == TEXT("CC_ROOT"))    { Anim->bRooted = !Anim->bRooted; return; }
	if (BoxName == TEXT("CC_SIL"))     { Anim->bSilenced = !Anim->bSilenced; return; }
	if (BoxName == TEXT("CC_DIS"))     { Anim->bDisarmed = !Anim->bDisarmed; return; }
	if (BoxName == TEXT("CC_FEAR"))    { Anim->bFeared = !Anim->bFeared; return; }
	if (BoxName == TEXT("CC_STASIS"))  { Anim->bStasis = !Anim->bStasis; return; }

	if (BoxName == TEXT("ACT_RESPAWN"))  { Anim->TriggerRespawn(); return; }
	if (BoxName == TEXT("ACT_DIALOGUE")) { Op->TriggerDialoguePerformance(); return; }
	if (BoxName == TEXT("ACT_RESET"))    { Op->ResetOperativeFull(FVector(0.0f, 0.0f, 90.0f), 0.0f); return; }
	if (BoxName == TEXT("ACT_SHOWCASE"))
	{
		if (GM->bShowcaseRunning) { GM->StopDeterministicShowcase(); }
		else { GM->StartDeterministicShowcase(); }
		return;
	}

	// 96-Clip Browser Handlers
	if (BoxName == TEXT("BRW_CLR"))  { ClearSearch(); return; }
	if (BoxName == TEXT("BRW_EXIT")) { Anim->ExitDirectClipMode(); return; }
	if (BoxName == TEXT("BRW_UP"))   { ScrollBrowser(-6); return; }
	if (BoxName == TEXT("BRW_DN"))   { ScrollBrowser(+6); return; }
	if (S.StartsWith(TEXT("PLAYCLIP_")))
	{
		const int32 ClipIdx = FCString::Atoi(*S.RightChop(9));
		if (ClipIdx >= 0 && ClipIdx < GMorphRigClipCount)
		{
			const FName CName(GMorphRigClips[ClipIdx].ClipId);
			if (CName == TEXT("dialogue")) { Op->TriggerDialoguePerformance(); }
			else { Anim->PlayDirectClip(CName); }
		}
		return;
	}

	// Face & Viseme Control Panel Handlers
	auto Cycle01 = [](float& Val)
	{
		if (Val < 0.25f) { Val = 0.5f; }
		else if (Val < 0.75f) { Val = 1.0f; }
		else { Val = 0.0f; }
	};
	FMorphRigFaceManualState& FM = Anim->FaceManual;
	if (BoxName == TEXT("FACE_TOG")) { FM.bEnableManualOverride = !FM.bEnableManualOverride; return; }
	if (BoxName == TEXT("FACE_RST")) { FM.Reset(); return; }

	if (S.StartsWith(TEXT("FC_")) || S.StartsWith(TEXT("PRE_")) || S.StartsWith(TEXT("VIS_")))
	{
		FM.bEnableManualOverride = true;
		GM->SetCameraPreset(EMorphRigCameraPreset::FacialCloseUp);
		if (BoxName == TEXT("FC_BL_L")) { Cycle01(FM.BlinkL); }
		else if (BoxName == TEXT("FC_BL_R")) { Cycle01(FM.BlinkR); }
		else if (BoxName == TEXT("FC_SQ_L")) { Cycle01(FM.SquintL); }
		else if (BoxName == TEXT("FC_SQ_R")) { Cycle01(FM.SquintR); }
		else if (BoxName == TEXT("FC_BU_L")) { Cycle01(FM.BrowUpL); }
		else if (BoxName == TEXT("FC_BU_R")) { Cycle01(FM.BrowUpR); }
		else if (BoxName == TEXT("FC_BD_L")) { Cycle01(FM.BrowDownL); }
		else if (BoxName == TEXT("FC_BD_R")) { Cycle01(FM.BrowDownR); }
		else if (BoxName == TEXT("FC_SM_L")) { Cycle01(FM.SmileL); }
		else if (BoxName == TEXT("FC_SM_R")) { Cycle01(FM.SmileR); }
		else if (BoxName == TEXT("FC_FR_L")) { Cycle01(FM.FrownL); }
		else if (BoxName == TEXT("FC_FR_R")) { Cycle01(FM.FrownR); }
		else if (BoxName == TEXT("FC_JAW"))  { Cycle01(FM.JawOpen); }
		else if (BoxName == TEXT("FC_LIP"))  { Cycle01(FM.LipClose); }
		else if (BoxName == TEXT("FC_PUK"))  { Cycle01(FM.MouthPucker); }
		else if (BoxName == TEXT("FC_TNG"))  { Cycle01(FM.TongueOut); }
		else if (BoxName == TEXT("FC_EYAW")) { FM.EyeYawDeg = (FM.EyeYawDeg < -10.0f) ? 0.0f : ((FM.EyeYawDeg < 10.0f) ? 22.0f : -22.0f); }
		else if (BoxName == TEXT("FC_EPIT")) { FM.EyePitchDeg = (FM.EyePitchDeg < -8.0f) ? 0.0f : ((FM.EyePitchDeg < 8.0f) ? 16.0f : -16.0f); }
		else if (S.StartsWith(TEXT("PRE_")))
		{
			static const TCHAR* Presets[6] = {
				TEXT("expr_joy_confidence"), TEXT("expr_anger"), TEXT("expr_concern_sadness"),
				TEXT("expr_surprise"), TEXT("expr_pain"), TEXT("expr_focus")
			};
			const int32 PIdx = FMath::Clamp(FCString::Atoi(*S.RightChop(4)), 0, 5);
			const FName PName(Presets[PIdx]);
			FM.ActivePreset = (FM.ActivePreset == PName) ? NAME_None : PName;
			FM.ActivePresetWeight = (FM.ActivePreset == NAME_None) ? 0.0f : 1.0f;
		}
		else if (S.StartsWith(TEXT("VIS_")))
		{
			static const TCHAR* Visemes[13] = {
				TEXT("V_SIL"), TEXT("V_MBP"), TEXT("V_FV"), TEXT("V_TH"), TEXT("V_TDNL"),
				TEXT("V_SZ"), TEXT("V_KG"), TEXT("V_AA"), TEXT("V_EE"), TEXT("V_EH"),
				TEXT("V_OH"), TEXT("V_OU"), TEXT("V_ER")
			};
			const int32 VIdx = FMath::Clamp(FCString::Atoi(*S.RightChop(4)), 0, 12);
			const FName VName(Visemes[VIdx]);
			FM.ActiveViseme = (FM.ActiveViseme == VName) ? NAME_None : VName;
			FM.ActiveVisemeWeight = (FM.ActiveViseme == NAME_None) ? 0.0f : 1.0f;
		}
	}
}
