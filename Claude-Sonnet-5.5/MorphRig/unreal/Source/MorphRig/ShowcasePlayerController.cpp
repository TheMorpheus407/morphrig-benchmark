#include "ShowcasePlayerController.h"
#include "ShowcaseRoom.h"
#include "ShowcaseDirector.h"
#include "ShowcasePanel.h"
#include "OperativeActionComponent.h"
#include "OperativeFaceComponent.h"
#include "OperativeAnimInstance.h"
#include "OperativeLibrary.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/InputComponent.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "EngineUtils.h"
#include "DrawDebugHelpers.h"
#include "GameFramework/PlayerInput.h"
#include "Kismet/GameplayStatics.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SWeakWidget.h"

AShowcasePlayerController::AShowcasePlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	bEnableMouseOverEvents = false;
	PrimaryActorTick.bCanEverTick = true;
	DefaultMouseCursor = EMouseCursor::Crosshairs;
}

AOperativeCharacter* AShowcasePlayerController::GetOperative() const
{
	return Cast<AOperativeCharacter>(GetPawn());
}

UOperativeActionComponent* AShowcasePlayerController::GetActions() const
{
	const AOperativeCharacter* O = GetOperative();
	return O ? O->Actions.Get() : nullptr;
}

AShowcaseDirector* AShowcasePlayerController::GetDirector() const
{
	return Director.Get();
}

void AShowcasePlayerController::SetDirector(AShowcaseDirector* D)
{
	Director = D;
}

AShowcaseRoom* AShowcasePlayerController::GetRoom() const
{
	TActorIterator<AShowcaseRoom> It(GetWorld());
	return It ? *It : nullptr;
}

// ------------------------------------------------------------------------------------------------ setup

void AShowcasePlayerController::BeginPlay()
{
	Super::BeginPlay();
	BuildBindings();
	EnsureCamera();
	FInputModeGameAndUI Mode;
	Mode.SetHideCursorDuringCapture(false);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(Mode);
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AShowcaseDirector* D = GetWorld()->SpawnActor<AShowcaseDirector>(FVector::ZeroVector, FRotator::ZeroRotator, SP);
	SetDirector(D);
	const bool bNoPanel = FParse::Param(FCommandLine::Get(), TEXT("NoPanel")) || FParse::Param(FCommandLine::Get(), TEXT("NoUI"));
	const bool bCapturing = D && D->IsCapturing();
	if (!bNoPanel && !bCapturing && FSlateApplication::IsInitialized())
	{
		Panel = SNew(SShowcasePanel).Controller(this);
		if (GEngine && GEngine->GameViewport)
		{
			PanelHolder = SNew(SWeakWidget).PossiblyNullContent(Panel.ToSharedRef());
			GEngine->GameViewport->AddViewportWidgetContent(PanelHolder.ToSharedRef(), 10);
		}
	}
	bPanelVisible = Panel.IsValid();
	int32 N = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("Instances="), N) && N > 1) SetInstances(N);
	if (FParse::Value(FCommandLine::Get(), TEXT("RenderMode="), N)) SetRenderMode(N);
	if (FParse::Value(FCommandLine::Get(), TEXT("LOD="), N)) SetLOD(N);
	if (FParse::Value(FCommandLine::Get(), TEXT("Team="), N)) SetTeam(N == 1 ? EOperativeTeam::B : EOperativeTeam::A);
	if (FParse::Value(FCommandLine::Get(), TEXT("View="), N)) SetView(static_cast<EShowcaseView>(FMath::Clamp(N, 0, 6)));
	if (FParse::Value(FCommandLine::Get(), TEXT("Overlay="), N)) SetOverlayMode(N);
	if (FParse::Param(FCommandLine::Get(), TEXT("NoOutline"))) { bOutline = true; ToggleOutline(); }
	if (FParse::Param(FCommandLine::Get(), TEXT("Studio")) && GetRoom()) GetRoom()->SetStudioMode(true);
}

void AShowcasePlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
	if (PanelHolder.IsValid() && GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(PanelHolder.ToSharedRef());
	}
	PanelHolder.Reset();
	Panel.Reset();
	Super::EndPlay(Reason);
}

void AShowcasePlayerController::EnsureCamera()
{
	if (CameraActor) return;
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	CameraActor = GetWorld()->SpawnActor<ACameraActor>(FVector(-300.f, 0.f, 200.f), FRotator::ZeroRotator, SP);
	if (CameraActor)
	{
		CameraActor->GetCameraComponent()->bConstrainAspectRatio = false;
		CameraActor->GetCameraComponent()->SetFieldOfView(60.f);
		SetViewTarget(CameraActor);
		bCameraSnap = true;
	}
}

void AShowcasePlayerController::AddDoc(const TCHAR* Category, const TCHAR* Keys, const TCHAR* Desc)
{
	FShowcaseBinding B;
	B.Category = Category;
	B.KeyText = Keys;
	B.Description = Desc;
	Bindings.Add(B);
}

void AShowcasePlayerController::Bind(const FKey& Key, EInputEvent Ev, TFunction<void()> Fn, bool bShift, bool bCtrl, bool bAlt)
{
	if (!InputComponent) return;
	FInputKeyBinding KB(FInputChord(Key, bShift, bCtrl, bAlt, false), Ev);
	KB.KeyDelegate.GetDelegateForManualSet().BindLambda([Fn]() { if (Fn) Fn(); });
	InputComponent->KeyBindings.Emplace(MoveTemp(KB));
}

void AShowcasePlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
}

void AShowcasePlayerController::BuildBindings()
{
	if (!InputComponent) return;
	Bindings.Reset();
	auto Seq = [this]() { return bSequenceControl; };
	auto Cmd = [this, Seq](TFunction<void()> F) { return TFunction<void()>([this, Seq, F]() { if (!Seq()) F(); }); };

	AddDoc(TEXT("Locomotion"), TEXT("W A S D"), TEXT("move relative to the camera (independent facing: the body turns to the aim, gait follows the direction)"));
	AddDoc(TEXT("Locomotion"), TEXT("Shift / Ctrl"), TEXT("sprint (650 cm/s) / walk (150 cm/s); default run (400 cm/s)"));
	AddDoc(TEXT("Locomotion"), TEXT("Mouse"), TEXT("aim point (floor, targets); RMB hold or Caps Lock = aim pose while moving"));
	AddDoc(TEXT("Locomotion"), TEXT("Q"), TEXT("facing mode: aim / movement / locked"));
	Bind(EKeys::SpaceBar, IE_Pressed, Cmd([this]() { CmdJump(); }));
	AddDoc(TEXT("Mobility"), TEXT("Space"), TEXT("jump (jump_start, air, land; long fall gives fall and heavy landing)"));
	Bind(EKeys::V, IE_Pressed, Cmd([this]() { CmdDash(); }));
	AddDoc(TEXT("Mobility"), TEXT("V"), TEXT("dash 2 m (root motion of dash_f/b/l/r, direction from WASD relative to the body)"));
	Bind(EKeys::B, IE_Pressed, Cmd([this]() { CmdBlink(); }));
	AddDoc(TEXT("Mobility"), TEXT("B"), TEXT("blink 6 m towards the movement direction (teleport is an event)"));
	Bind(EKeys::Q, IE_Pressed, Cmd([this]() { CycleFacingMode(); }));
	Bind(EKeys::RightMouseButton, IE_Pressed, Cmd([this]() { SetAimToggle(false); }));
	Bind(EKeys::CapsLock, IE_Pressed, Cmd([this]() { ToggleAimHold(); }));

	Bind(EKeys::LeftMouseButton, IE_Pressed, Cmd([this]() { CmdFire(); }));
	AddDoc(TEXT("Combat"), TEXT("LMB"), TEXT("ranged fire (upper body layer, works while moving)"));
	Bind(EKeys::F, IE_Pressed, Cmd([this]() { CmdBurst(); }));
	AddDoc(TEXT("Combat"), TEXT("F"), TEXT("three shot burst"));
	Bind(EKeys::E, IE_Pressed, Cmd([this]() { CmdMelee(); }));
	AddDoc(TEXT("Combat"), TEXT("E"), TEXT("forearm blade: press again inside the combo window for melee 2 and 3"));
	Bind(EKeys::R, IE_Pressed, Cmd([this]() { CmdReload(); }));
	AddDoc(TEXT("Combat"), TEXT("R"), TEXT("reload (power cell out of the forearm slot, from the pouch, back in)"));
	Bind(EKeys::One, IE_Pressed, Cmd([this]() { CmdCastDirectional(); }));
	Bind(EKeys::Two, IE_Pressed, Cmd([this]() { CmdCastGround(); }));
	Bind(EKeys::Three, IE_Pressed, Cmd([this]() { CmdCastSelf(); }));
	AddDoc(TEXT("Casts"), TEXT("1 / 2 / 3"), TEXT("directional cast (moving) / ground cast at the cursor / self cast"));
	Bind(EKeys::Four, IE_Pressed, Cmd([this]() { CmdChannelPressed(); }));
	Bind(EKeys::Four, IE_Released, Cmd([this]() { CmdChannelReleased(); }));
	AddDoc(TEXT("Casts"), TEXT("4 (hold)"), TEXT("channel: start, sustain while held, release ends it, X interrupts at any point"));
	Bind(EKeys::Five, IE_Pressed, Cmd([this]() { CmdChargePressed(); }));
	Bind(EKeys::Five, IE_Released, Cmd([this]() { CmdChargeReleased(); }));
	Bind(EKeys::C, IE_Pressed, Cmd([this]() { CmdChargeCancel(); }));
	AddDoc(TEXT("Casts"), TEXT("5 (hold) / C"), TEXT("charge: release at any time fires, C cancels"));
	Bind(EKeys::Six, IE_Pressed, Cmd([this]() { CmdDeploy(); }));
	AddDoc(TEXT("Casts"), TEXT("6"), TEXT("deploy the beacon (attached prop spawns as a world beacon at the release event)"));
	Bind(EKeys::Seven, IE_Pressed, Cmd([this]() { CmdUplink(); }));
	AddDoc(TEXT("Casts"), TEXT("7"), TEXT("uplink (3 s recall gesture); 7 again or X cancels"));
	Bind(EKeys::X, IE_Pressed, Cmd([this]() { CmdInterrupt(); }));
	AddDoc(TEXT("Casts"), TEXT("X"), TEXT("interrupt channel / uplink / charge, stop emote and speech"));
	Bind(EKeys::G, IE_Pressed, Cmd([this]() { CmdGreet(); }));
	Bind(EKeys::H, IE_Pressed, Cmd([this]() { CmdVictory(); }));
	Bind(EKeys::O, IE_Pressed, Cmd([this]() { CmdDefeat(); }));
	Bind(EKeys::P, IE_Pressed, Cmd([this]() { CmdDialogue(); }));
	AddDoc(TEXT("Emotes"), TEXT("G / H / O / P"), TEXT("greet / victory / defeat / speech sample (dialogue clip and audio, face view)"));

	Bind(EKeys::Up, IE_Pressed, Cmd([this]() { CmdHit(0); }));
	Bind(EKeys::Down, IE_Pressed, Cmd([this]() { CmdHit(1); }));
	Bind(EKeys::Left, IE_Pressed, Cmd([this]() { CmdHit(2); }));
	Bind(EKeys::Right, IE_Pressed, Cmd([this]() { CmdHit(3); }));
	AddDoc(TEXT("Hits and disables"), TEXT("Up Down Left Right"), TEXT("directional additive hit reaction: from front / back / left / right"));
	Bind(EKeys::T, IE_Pressed, Cmd([this]() { CmdStun(); }));
	Bind(EKeys::Y, IE_Pressed, Cmd([this]() { CmdSleepToggle(); }));
	Bind(EKeys::N, IE_Pressed, Cmd([this]() { CmdKnockback(); }));
	Bind(EKeys::U, IE_Pressed, Cmd([this]() { CmdKnockup(); }));
	Bind(EKeys::J, IE_Pressed, Cmd([this]() { CmdKnockdown(true); }));
	Bind(EKeys::Z, IE_Pressed, Cmd([this]() { CmdKnockdown(false); }));
	AddDoc(TEXT("Hits and disables"), TEXT("T / Y / N / U"), TEXT("stun / sleep and wake / knockback / knockup"));
	AddDoc(TEXT("Hits and disables"), TEXT("J / Z"), TEXT("knockdown from a front hit (lands face up) / from a back hit (face down), then prone and getup"));
	Bind(EKeys::K, IE_Pressed, Cmd([this]() { CmdKill(); }));
	Bind(EKeys::L, IE_Pressed, Cmd([this]() { CmdRespawn(); }));
	Bind(EKeys::BackSpace, IE_Pressed, Cmd([this]() { CmdReset(); }));
	AddDoc(TEXT("Hits and disables"), TEXT("K / L / Backspace"), TEXT("kill (death once) / respawn / reset the character"));
	Bind(EKeys::F9, IE_Pressed, Cmd([this]() { CmdToggleRoot(); }));
	Bind(EKeys::F10, IE_Pressed, Cmd([this]() { CmdToggleSilence(); }));
	Bind(EKeys::F11, IE_Pressed, Cmd([this]() { CmdToggleDisarm(); }));
	Bind(EKeys::F12, IE_Pressed, Cmd([this]() { CmdToggleStasis(); }));
	AddDoc(TEXT("Hits and disables"), TEXT("F9 F10 F11 F12"), TEXT("toggle root / silence / disarm / stasis"));
	Bind(EKeys::Hyphen, IE_Pressed, Cmd([this]() { AdjustActionRate(-0.125f); }));
	Bind(EKeys::Equals, IE_Pressed, Cmd([this]() { AdjustActionRate(0.125f); }));
	AddDoc(TEXT("Animation"), TEXT("- / ="), TEXT("action rate 0.5x .. 1.5x (events scale with it and never duplicate)"));
	Bind(EKeys::M, IE_Pressed, [this]() { ToggleMotionViewerStation(); });
	AddDoc(TEXT("Animation"), TEXT("M"), TEXT("motion viewer: character to the pedestal, animation browser plays any of the 96 clips"));
	Bind(EKeys::Escape, IE_Pressed, [this]() { BrowserStop(); });

	AddDoc(TEXT("Views"), TEXT("Tab"), TEXT("cycle views (third person / front / side / top-down / face / hands)"));
	Bind(EKeys::Tab, IE_Pressed, [this]() { CycleView(); });
	Bind(EKeys::Home, IE_Pressed, [this]() { SetView(EShowcaseView::ThirdPerson); });
	Bind(EKeys::PageUp, IE_Pressed, [this]() { SetView(EShowcaseView::Front); });
	Bind(EKeys::PageDown, IE_Pressed, [this]() { SetView(EShowcaseView::Side); });
	Bind(EKeys::End, IE_Pressed, [this]() { SetView(EShowcaseView::TopDown); });
	Bind(EKeys::Insert, IE_Pressed, [this]() { SetView(EShowcaseView::Face); });
	Bind(EKeys::Delete, IE_Pressed, [this]() { SetView(EShowcaseView::Hands); });
	AddDoc(TEXT("Views"), TEXT("Home PgUp PgDn End Ins Del"), TEXT("third person / front / side / top-down / face / hands (prop contact)"));
	AddDoc(TEXT("Views"), TEXT("MMB drag, wheel"), TEXT("orbit and zoom in the orbiting views"));
	Bind(EKeys::F1, IE_Pressed, [this]() { ToggleHelp(); });
	Bind(EKeys::F2, IE_Pressed, [this]() { TogglePanel(); });
	Bind(EKeys::F3, IE_Pressed, [this]() { ToggleOverlay(); });
	Bind(EKeys::F4, IE_Pressed, [this]() { CycleRenderMode(); });
	Bind(EKeys::F5, IE_Pressed, [this]() { CycleLOD(); });
	Bind(EKeys::F6, IE_Pressed, [this]() { ToggleTeam(); });
	Bind(EKeys::F7, IE_Pressed, [this]() { ToggleInstances(); });
	Bind(EKeys::F8, IE_Pressed, [this]() { StartSequence(); });
	AddDoc(TEXT("Display"), TEXT("F1 F2 F3"), TEXT("help overlay / panel / overlays (skeleton, sockets, foot IK, aim and look rays)"));
	AddDoc(TEXT("Display"), TEXT("F4 F5 F6"), TEXT("render mode (textured, normals, wireframe, clay) / forced LOD (auto, 0, 1, 2) / team A or B"));
	AddDoc(TEXT("Display"), TEXT("F7 F8"), TEXT("1 or 10 animated Operatives / start the deterministic showcase sequence"));
	Bind(EKeys::Semicolon, IE_Pressed, [this]() { ToggleOutline(); });
	AddDoc(TEXT("Display"), TEXT("; (semicolon)"), TEXT("team outline on / off (the icon on the suit stays; the face view draws without the outline)"));
	Bind(EKeys::Zero, IE_Pressed, [this]() { ToggleStudio(); });
	AddDoc(TEXT("Display"), TEXT("0"), TEXT("studio backdrop (plain floor and background, test props hidden) / test room"));
	Bind(EKeys::Comma, IE_Pressed, [this]() { SelectNextTarget(); });
	Bind(EKeys::Period, IE_Pressed, [this]() { MoveSelectedTargetToCursor(); });
	Bind(EKeys::I, IE_Pressed, [this]() { ToggleTargetsPatrol(); });
	AddDoc(TEXT("Targets"), TEXT(", . I"), TEXT("select next target / move the selected target to the cursor / patrol on and off"));
	Bind(EKeys::MouseScrollUp, IE_Pressed, [this]() { OrbitDistance = FMath::Clamp(OrbitDistance * 0.9f, 80.f, 3500.f); });
	Bind(EKeys::MouseScrollDown, IE_Pressed, [this]() { OrbitDistance = FMath::Clamp(OrbitDistance * 1.1f, 80.f, 3500.f); });
	Bind(EKeys::MiddleMouseButton, IE_Pressed, [this]() { bOrbitDrag = true; });
	Bind(EKeys::MiddleMouseButton, IE_Released, [this]() { bOrbitDrag = false; });
	Bind(EKeys::Enter, IE_Pressed, [this]() { CmdDialogue(); });
}

// ------------------------------------------------------------------------------------------------ per frame

FVector AShowcasePlayerController::CameraForwardFlat() const
{
	FRotator R = FRotator::ZeroRotator;
	if (PlayerCameraManager) R = PlayerCameraManager->GetCameraRotation();
	R.Pitch = 0.f;
	R.Roll = 0.f;
	return R.Vector();
}

float AShowcasePlayerController::CurrentGaitSpeed() const
{
	if (IsInputKeyDown(EKeys::LeftShift) || IsInputKeyDown(EKeys::RightShift)) return OperativeConst::SprintSpeed;
	if (IsInputKeyDown(EKeys::LeftControl) || IsInputKeyDown(EKeys::RightControl)) return OperativeConst::WalkSpeed;
	switch (Gait)
	{
	case EOperativeGait::Walk: return OperativeConst::WalkSpeed;
	case EOperativeGait::Sprint: return OperativeConst::SprintSpeed;
	default: return OperativeConst::RunSpeed;
	}
}

void AShowcasePlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	AOperativeCharacter* O = GetOperative();
	if (!O) return;
	if (bOrbitDrag)
	{
		float DX = 0.f, DY = 0.f;
		GetInputMouseDelta(DX, DY);
		OrbitYaw += DX * 0.25f;
		OrbitPitch = FMath::Clamp(OrbitPitch + DY * 0.25f, -85.f, 60.f);
	}
	UpdateMovement(DeltaTime);
	UpdateAim(DeltaTime);
	UpdateCamera(DeltaTime);
	UpdateOverlays();
}

void AShowcasePlayerController::UpdateMovement(float Dt)
{
	AOperativeCharacter* O = GetOperative();
	if (O->bAutopilot) return;      // performance runs let the main Operative follow the same autopilot loop as the other instances
	FVector Dir = FVector::ZeroVector;
	float Speed = 0.f;
	if (bSequenceControl)
	{
		Dir = SequenceMoveDir;
		Speed = SequenceMoveSpeed;
	}
	else if (bManualLoco)
	{
		Dir = FRotator(0.f, O->GetActorRotation().Yaw - ManualAngle, 0.f).Vector();
		Speed = ManualSpeed;
	}
	else
	{
		const float F = (IsInputKeyDown(EKeys::W) ? 1.f : 0.f) - (IsInputKeyDown(EKeys::S) ? 1.f : 0.f);
		const float R = (IsInputKeyDown(EKeys::D) ? 1.f : 0.f) - (IsInputKeyDown(EKeys::A) ? 1.f : 0.f);
		const FVector Fwd = CameraForwardFlat();
		const FVector Right = FRotator(0.f, Fwd.Rotation().Yaw + 90.f, 0.f).Vector();
		Dir = Fwd * F + Right * R;
		Speed = Dir.IsNearlyZero() ? 0.f : CurrentGaitSpeed();
	}
	O->SetMoveIntent(Dir, Speed);
}

void AShowcasePlayerController::UpdateAim(float Dt)
{
	AOperativeCharacter* O = GetOperative();
	if (O->bAutopilot) return;
	UOperativeActionComponent* A = O->Actions;
	const FVector Origin = O->GetAimOrigin();
	if (bSequenceControl)
	{
		AimPoint = SequenceAimPoint;
	}
	else if (bManualAim)
	{
		const FRotator R(ManualAimPitch, O->GetActorRotation().Yaw - ManualAimYaw, 0.f);
		AimPoint = Origin + R.Vector() * 600.f;
	}
	else if (bCursorAim)
	{
		FVector Loc, Dir;
		if (DeprojectMousePositionToWorld(Loc, Dir))
		{
			// intersection of the mouse ray with the horizontal plane through the chest (level aim)
			FVector Plane = AimPoint;
			if (!FMath::IsNearlyZero(Dir.Z))
			{
				const float T = (Origin.Z - Loc.Z) / Dir.Z;
				if (T > 0.f) Plane = Loc + Dir * T;
			}
			AimPoint = Plane;
			FHitResult Hit;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(ShowcaseAim), false, O);
			if (GetWorld()->LineTraceSingleByChannel(Hit, Loc, Loc + Dir * 20000.f, ECC_Visibility, Params) && Hit.bBlockingHit)
			{
				const bool bSolidThing = Cast<AShowcaseTarget>(Hit.GetActor()) != nullptr || Hit.ImpactNormal.Z < 0.6f;
				if (bSolidThing) AimPoint = Hit.ImpactPoint;
			}
		}
	}
	else
	{
		AimPoint = Origin + O->GetActorForwardVector() * 600.f;
	}
	O->SetAimPoint(AimPoint);
	const bool bRmb = !bSequenceControl && IsInputKeyDown(EKeys::RightMouseButton);
	A->SetAimHold(bRmb || bAimToggle);
	if (bLookAtCamera && PlayerCameraManager)
	{
		A->SetLookTarget(PlayerCameraManager->GetCameraLocation(), true);
	}
}

void AShowcasePlayerController::UpdateCamera(float Dt)
{
	EnsureCamera();
	AOperativeCharacter* O = GetOperative();
	if (!CameraActor || !O) return;
	const bool bSnap = bCameraSnap;
	bCameraSnap = false;
	FVector Focus = O->GetActorLocation() + FVector(0.f, 0.f, 20.f);   // chest level
	FVector Loc;
	FRotator Rot;
	float Fov = 60.f;
	const FRotator Facing(0.f, O->GetActorRotation().Yaw, 0.f);
	switch (View)
	{
	case EShowcaseView::ThirdPerson:
	{
		float Dist = OrbitDistance;
		if (InstanceCount > 1)
		{
			FVector Sum = FVector::ZeroVector;
			int32 N = 1;
			Sum = O->GetActorLocation();
			for (AOperativeCharacter* E : ExtraOperatives) if (E) { Sum += E->GetActorLocation(); ++N; }
			const FVector Centre = Sum / N;
			float R = 0.f;
			R = FVector::Dist2D(O->GetActorLocation(), Centre);
			for (AOperativeCharacter* E : ExtraOperatives) if (E) R = FMath::Max(R, FVector::Dist2D(E->GetActorLocation(), Centre));
			Focus = Centre + FVector(0.f, 0.f, 60.f);
			Dist = FMath::Max(OrbitDistance, R * 2.4f + 380.f);
		}
		else
		{
			// mid body: head to boots stay in the frame at the default distance. The height follows the pelvis, so a body that lies on the floor
			// (knockdown, prone, death) stays in the middle of the frame while the capsule keeps standing
			const FVector Actor = O->GetActorLocation();
			float FocusZ = Actor.Z + 6.f;
			FTransform Pelvis;
			if (O->GetSocketTransformSafe(FName("pelvis"), Pelvis)) FocusZ = FMath::Clamp(Pelvis.GetLocation().Z + 2.f, Actor.Z - 90.f + 14.f, Actor.Z + 60.f);
			Focus = FVector(Actor.X, Actor.Y, FocusZ);
		}
		const FRotator Orbit(OrbitPitch, OrbitYaw, 0.f);
		Loc = Focus - Orbit.Vector() * Dist;
		Rot = (Focus - Loc).Rotation();
		Fov = 55.f;
		break;
	}
	case EShowcaseView::Front:
	{
		const FVector Centre = O->GetActorLocation() + FVector(0.f, 0.f, 2.f);
		Loc = Centre + Facing.Vector() * OrbitDistance;
		Loc.Z += 10.f;
		Rot = (Centre - Loc).Rotation();
		Fov = 44.f;
		break;
	}
	case EShowcaseView::Side:
	{
		const FVector Centre = O->GetActorLocation() + FVector(0.f, 0.f, 2.f);
		const FVector Right = FRotator(0.f, Facing.Yaw + 90.f, 0.f).Vector();
		Loc = Centre + Right * OrbitDistance;
		Loc.Z += 10.f;
		Rot = (Centre - Loc).Rotation();
		Fov = 44.f;
		break;
	}
	case EShowcaseView::TopDown:
	{
		const float Pitch = -55.f;
		const FRotator Orbit(Pitch, OrbitYaw, 0.f);
		const float Dist = OrbitDistance > 1000.f ? OrbitDistance : 1580.f;
		const FVector F2 = O->GetActorLocation();
		Loc = F2 - Orbit.Vector() * Dist;
		Rot = Orbit;
		Fov = 55.f;      // 55 degrees down at 1580 cm with a 55 degree field of view: the character is about 120 px tall in a 1920 px wide frame
		break;
	}
	case EShowcaseView::Face:
	{
		FTransform Head;
		FVector Eyes = O->GetActorLocation() + FVector(0.f, 0.f, 78.f);
		if (O->GetSocketTransformSafe(FName("eye_l"), Head))
		{
			Eyes = Head.GetLocation();
			FTransform HR;
			if (O->GetSocketTransformSafe(FName("eye_r"), HR)) Eyes = (Eyes + HR.GetLocation()) * 0.5f;
		}
		// portrait framing: hair line to chin fit the frame with a margin below for the subtitle; the camera stands 9 degrees to the
		// character's right of its facing so the nose and the lips read in relief
		const FVector FaceFocus = Eyes + FVector(0.f, 0.f, -1.5f);
		const FVector Dir = FRotator(0.f, O->GetActorRotation().Yaw + FaceCameraYaw, 0.f).Vector();
		Loc = FaceFocus + Dir * 118.f + FVector(0.f, 0.f, 1.f);
		Rot = (FaceFocus - Loc).Rotation();
		Fov = 24.f;
		break;
	}
	case EShowcaseView::Orbit:
	{
		const FVector Centre = O->GetActorLocation() + FVector(0.f, 0.f, 0.f);
		const FRotator Orbit(OrbitPitch, OrbitYaw, 0.f);
		Loc = Centre - Orbit.Vector() * OrbitDistance;
		Rot = (Centre - Loc).Rotation();
		Fov = 30.f;
		break;
	}
	case EShowcaseView::Hands:
	{
		FTransform Hand;
		FVector C = O->GetActorLocation() + FVector(0.f, 0.f, 10.f);
		if (O->GetSocketTransformSafe(FName("cell_slot"), Hand)) C = Hand.GetLocation();
		FTransform Beacon;
		if (O->GetSocketTransformSafe(FName("prop_beacon"), Beacon)) C = (C * 2.f + Beacon.GetLocation()) / 3.f;
		const FRotator Orbit(-10.f, Facing.Yaw - 55.f, 0.f);
		Loc = C - Orbit.Vector() * 150.f;
		Rot = (C - Loc).Rotation();
		Fov = 40.f;
		break;
	}
	}
	// keep the camera inside the room: when the wanted position is behind a wall, the ramp or a target, the camera swings around the character to
	// the nearest free direction (it moves only when its current direction is blocked and comes back after 0.6 s of a free original direction);
	// a final sweep keeps it out of any geometry that is left
	if (bCameraAvoid && (View == EShowcaseView::ThirdPerson || View == EShowcaseView::Front || View == EShowcaseView::Side || View == EShowcaseView::Orbit))
	{
		const FVector Pivot = O->GetActorLocation() + FVector(0.f, 0.f, 70.f);
		const FVector LookAt = (View == EShowcaseView::ThirdPerson) ? Focus : O->GetActorLocation() + FVector(0.f, 0.f, 2.f);
		FCollisionQueryParams Q(SCENE_QUERY_STAT(ShowcaseCamera), false, O);
		for (AOperativeCharacter* E : ExtraOperatives) if (E) Q.AddIgnoredActor(E);
		const FCollisionShape Ball = FCollisionShape::MakeSphere(20.f);
		const FVector Wanted = Loc;
		auto Place = [&](float YawOffset) { return Pivot + FRotator(0.f, YawOffset, 0.f).RotateVector(Wanted - Pivot); };
		auto Clear = [&](float YawOffset) -> bool
		{
			FHitResult H;
			return !GetWorld()->SweepSingleByChannel(H, Pivot, Place(YawOffset), FQuat::Identity, ECC_Camera, Ball, Q);
		};
		if (bSnap) CamAvoidYaw = CamAvoidTarget;
		if (!Clear(CamAvoidYaw))
		{
			CamClearTime = 0.f;
			bool bFound = false;
			for (float Step = 0.f; Step <= 180.f && !bFound; Step += 20.f)
			{
				for (const float Sgn : { 1.f, -1.f })
				{
					if (Step == 0.f && Sgn < 0.f) continue;
					if (Clear(Sgn * Step)) { CamAvoidTarget = Sgn * Step; bFound = true; break; }
				}
			}
		}
		else if (CamAvoidTarget != 0.f)
		{
			CamClearTime = Clear(0.f) ? CamClearTime + Dt : 0.f;
			if (CamClearTime > 0.6f) { CamAvoidTarget = 0.f; CamClearTime = 0.f; }
		}
		CamAvoidYaw = bSnap ? CamAvoidTarget : FMath::FixedTurn(CamAvoidYaw, CamAvoidTarget, 220.f * Dt);
		Loc = Place(CamAvoidYaw);
		FHitResult Hit;
		if (GetWorld()->SweepSingleByChannel(Hit, Pivot, Loc, FQuat::Identity, ECC_Camera, Ball, Q)) Loc = Hit.Location;
		Rot = (LookAt - Loc).Rotation();
	}
	const float A = bSnap ? 1.f : 1.f - FMath::Exp(-Dt * 9.f);
	const FVector CurLoc = CameraActor->GetActorLocation();
	const FRotator CurRot = CameraActor->GetActorRotation();
	const FVector NewLoc = FMath::Lerp(CurLoc, Loc, A);
	const FRotator NewRot = FQuat::Slerp(CurRot.Quaternion(), Rot.Quaternion(), A).Rotator();
	CameraActor->SetActorLocationAndRotation(NewLoc, NewRot);
	UCameraComponent* Cam = CameraActor->GetCameraComponent();
	Cam->SetFieldOfView(FMath::Lerp(Cam->FieldOfView, Fov, A));
	// projected character height (top-down readability check)
	FVector2D Head2D, Feet2D;
	FTransform HT;
	FVector HeadPos = O->GetActorLocation() + FVector(0.f, 0.f, 90.f);
	if (O->GetSocketTransformSafe(FName("fx_head_top"), HT)) HeadPos = HT.GetLocation();
	const FVector FeetPos = O->GetActorLocation() - FVector(0.f, 0.f, 90.f);
	if (ProjectWorldLocationToScreen(HeadPos, Head2D) && ProjectWorldLocationToScreen(FeetPos, Feet2D))
	{
		HeadScreen = Head2D;
		FeetScreen = Feet2D;
		CharacterPixelHeight = FVector2D::Distance(Head2D, Feet2D);
	}
}

void AShowcasePlayerController::UpdateOverlays()
{
	if (OverlayMode == 0) return;
	AOperativeCharacter* O = GetOperative();
	UWorld* W = GetWorld();
	USkeletalMeshComponent* M = O->GetMesh();
	if (!M || !M->GetSkeletalMeshAsset()) return;
	auto DrawChar = [&](AOperativeCharacter* C)
	{
		USkeletalMeshComponent* Mesh = C->GetMesh();
		if (!Mesh || !Mesh->GetSkeletalMeshAsset() || !C->IsMeshVisible()) return;
		if (OverlayMode == 1 || OverlayMode == 3)
		{
			const FReferenceSkeleton& Ref = Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
			for (int32 B = 1; B < Ref.GetNum(); ++B)
			{
				const int32 P = Ref.GetParentIndex(B);
				const FName Name = Ref.GetBoneName(B);
				const FString S = Name.ToString();
				if (S.StartsWith(TEXT("prop_"))) continue;
				const FVector A = Mesh->GetBoneLocation(Ref.GetBoneName(P), EBoneSpaces::WorldSpace);
				const FVector Bp = Mesh->GetBoneLocation(Name, EBoneSpaces::WorldSpace);
				FColor Col = FColor(255, 255, 255);
				if (S.Contains(TEXT("_l")) && !S.StartsWith(TEXT("lid"))) Col = FColor(90, 200, 255);
				else if (S.EndsWith(TEXT("_r"))) Col = FColor(255, 120, 200);
				else if (S.StartsWith(TEXT("hair")) || S.StartsWith(TEXT("cable"))) Col = FColor(255, 220, 60);
				else if (S.StartsWith(TEXT("jaw")) || S.StartsWith(TEXT("tongue")) || S.StartsWith(TEXT("eye")) || S.StartsWith(TEXT("lid"))) Col = FColor(120, 255, 140);
				DrawDebugLine(W, A, Bp, Col, false, -1.f, SDPG_Foreground, 0.35f);
			}
		}
	};
	DrawChar(O);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) DrawChar(E);
	if (OverlayMode == 2 || OverlayMode == 3)
	{
		static const TCHAR* Sockets[] = { TEXT("hand_grip_l"), TEXT("hand_grip_r"), TEXT("emitter_muzzle"), TEXT("blade_base"), TEXT("blade_tip"), TEXT("cell_slot"), TEXT("cell_pouch"),
			TEXT("beacon_dock"), TEXT("prop_cell"), TEXT("prop_beacon"), TEXT("fx_chest"), TEXT("fx_back"), TEXT("fx_head_top"), TEXT("fx_mouth"), TEXT("cam_face"), TEXT("eye_l"), TEXT("eye_r") };
		for (const TCHAR* S : Sockets)
		{
			FTransform T;
			if (!O->GetSocketTransformSafe(FName(S), T)) continue;
			DrawDebugCoordinateSystem(W, T.GetLocation(), T.Rotator(), 6.f, false, -1.f, SDPG_Foreground, 0.4f);
			if (OverlayMode == 3) DrawDebugString(W, T.GetLocation() + FVector(0.f, 0.f, 4.f), S, nullptr, FColor::White, 0.f, false, 0.7f);
		}
		// foot IK targets: ground contact below the animated feet
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const FVector Foot = M->GetSocketLocation(Side == 0 ? FName("foot_l") : FName("foot_r"));
			FHitResult Hit;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(ShowcaseIKDraw), false, O);
			if (W->LineTraceSingleByChannel(Hit, FVector(Foot.X, Foot.Y, Foot.Z + 60.f), FVector(Foot.X, Foot.Y, Foot.Z - 60.f), ECC_Visibility, Params))
			{
				DrawDebugSphere(W, Hit.ImpactPoint, 3.f, 8, FColor::Green, false, -1.f, SDPG_Foreground, 0.3f);
				DrawDebugLine(W, Foot, Hit.ImpactPoint, FColor::Green, false, -1.f, SDPG_Foreground, 0.3f);
				DrawDebugLine(W, Hit.ImpactPoint, Hit.ImpactPoint + Hit.ImpactNormal * 12.f, FColor::Cyan, false, -1.f, SDPG_Foreground, 0.3f);
			}
		}
		// aim ray
		DrawDebugLine(W, O->GetMuzzleLocation(), AimPoint, FColor(255, 90, 60), false, -1.f, SDPG_Foreground, 0.4f);
		DrawDebugSphere(W, AimPoint, 6.f, 8, FColor(255, 90, 60), false, -1.f, SDPG_Foreground, 0.4f);
		// blade segment during the hit window
		FTransform B0, B1;
		if (GetActions() && GetActions()->IsMeleeWindowOpen() && O->GetSocketTransformSafe(FName("blade_base"), B0) && O->GetSocketTransformSafe(FName("blade_tip"), B1))
		{
			DrawDebugLine(W, B0.GetLocation(), B0.GetLocation() + (B1.GetLocation() - B0.GetLocation()).GetSafeNormal() * ((B1.GetLocation() - B0.GetLocation()).Size() + 30.f), FColor::Red, false, -1.f, SDPG_Foreground, 1.2f);
		}
	}
}

// ------------------------------------------------------------------------------------------------ commands

FVector AShowcasePlayerController::HitDirectionWorld(int32 Direction) const
{
	const AOperativeCharacter* O = GetOperative();
	const FRotator Facing(0.f, O ? O->GetActorRotation().Yaw : 0.f, 0.f);
	FVector From = Facing.Vector();                                            // front: attacker in front
	if (Direction == 1) From = -Facing.Vector();
	else if (Direction == 2) From = -FRotator(0.f, Facing.Yaw + 90.f, 0.f).Vector();   // character left is -Y (Unreal)
	else if (Direction == 3) From = FRotator(0.f, Facing.Yaw + 90.f, 0.f).Vector();
	return -From;    // travel direction of the hit
}

void AShowcasePlayerController::CmdJump() { if (auto* A = GetActions()) A->RequestJump(); }

void AShowcasePlayerController::CmdDash()
{
	AOperativeCharacter* O = GetOperative();
	if (!O) return;
	O->Actions->RequestDash(O->DesiredMoveDir);
}

void AShowcasePlayerController::CmdBlink()
{
	AOperativeCharacter* O = GetOperative();
	if (!O) return;
	O->Actions->RequestBlink(O->DesiredMoveDir.IsNearlyZero() ? O->GetActorForwardVector() : O->DesiredMoveDir, 600.f);
}

void AShowcasePlayerController::CmdFire() { if (auto* A = GetActions()) A->RequestFire(); }
void AShowcasePlayerController::CmdBurst() { if (auto* A = GetActions()) A->RequestBurst(); }
void AShowcasePlayerController::CmdMelee() { if (auto* A = GetActions()) A->RequestMelee(); }
void AShowcasePlayerController::CmdReload() { if (auto* A = GetActions()) A->RequestReload(); }
void AShowcasePlayerController::CmdCastDirectional() { if (auto* A = GetActions()) A->RequestCastDirectional(); }
void AShowcasePlayerController::CmdCastGround() { if (auto* A = GetActions()) A->RequestCastGround(); }
void AShowcasePlayerController::CmdCastSelf() { if (auto* A = GetActions()) A->RequestCastSelf(); }
void AShowcasePlayerController::CmdChannelPressed() { bChannelHeld = true; if (auto* A = GetActions()) A->RequestChannelStart(); }
void AShowcasePlayerController::CmdChannelReleased() { bChannelHeld = false; if (auto* A = GetActions()) A->RequestChannelRelease(); }
void AShowcasePlayerController::CmdChargePressed() { bChargeHeld = true; if (auto* A = GetActions()) A->RequestChargeStart(); }
void AShowcasePlayerController::CmdChargeReleased() { bChargeHeld = false; if (auto* A = GetActions()) A->RequestChargeRelease(); }
void AShowcasePlayerController::CmdChargeCancel() { if (auto* A = GetActions()) A->RequestChargeCancel(); }
void AShowcasePlayerController::CmdDeploy() { if (auto* A = GetActions()) A->RequestDeploy(); }

void AShowcasePlayerController::CmdUplink()
{
	UOperativeActionComponent* A = GetActions();
	if (!A) return;
	if (A->IsUplinkActive()) A->RequestUplinkCancel();
	else A->RequestUplinkStart();
}

void AShowcasePlayerController::CmdInterrupt()
{
	UOperativeActionComponent* A = GetActions();
	if (!A) return;
	if (A->GetActionKind() == EOperativeAction::Charge) A->RequestChargeCancel();
	else if (A->GetActionKind() == EOperativeAction::Uplink) A->RequestUplinkCancel();
	else A->InterruptAction(EOperativeInterrupt::Manual);
	if (A->IsViewerActive()) A->StopViewer();
}

void AShowcasePlayerController::CmdGreet() { if (auto* A = GetActions()) A->RequestEmote(EOperativeAction::Greet); }
void AShowcasePlayerController::CmdVictory() { if (auto* A = GetActions()) A->RequestEmote(EOperativeAction::Victory); }
void AShowcasePlayerController::CmdDefeat() { if (auto* A = GetActions()) A->RequestEmote(EOperativeAction::Defeat); }

void AShowcasePlayerController::CmdDialogue()
{
	UOperativeActionComponent* A = GetActions();
	if (!A) return;
	if (A->GetActionKind() == EOperativeAction::Dialogue) { A->StopDialogue(); return; }
	if (A->RequestDialogue()) SetView(EShowcaseView::Face);
}

void AShowcasePlayerController::CmdHit(int32 Direction)
{
	if (UOperativeActionComponent* A = GetActions()) A->ApplyHit(HitDirectionWorld(Direction), 0.f);
}

void AShowcasePlayerController::CmdStun() { if (auto* A = GetActions()) A->ApplyStun(2.0f); }

void AShowcasePlayerController::CmdSleepToggle()
{
	UOperativeActionComponent* A = GetActions();
	if (!A) return;
	if (A->GetState() == EOperativeState::Sleep) A->WakeUp();
	else A->ApplySleep(0.f);
}

void AShowcasePlayerController::CmdKnockback() { if (auto* A = GetActions()) A->ApplyKnockback(HitDirectionWorld(0), 260.f); }
void AShowcasePlayerController::CmdKnockup() { if (auto* A = GetActions()) A->ApplyKnockup(HitDirectionWorld(0), 900.f); }
void AShowcasePlayerController::CmdKnockdown(bool bHitFromFront) { if (auto* A = GetActions()) A->ApplyKnockdown(HitDirectionWorld(bHitFromFront ? 0 : 1)); }
void AShowcasePlayerController::CmdKill() { if (auto* A = GetActions()) A->Kill(HitDirectionWorld(IsInputKeyDown(EKeys::LeftShift) ? 1 : 0)); }
void AShowcasePlayerController::CmdRespawn() { if (auto* A = GetActions()) A->Respawn(); }

void AShowcasePlayerController::CmdReset()
{
	if (AOperativeCharacter* O = GetOperative()) O->ResetOperative(true);
	bSleeping = false;
	bManualLoco = false;
	bManualAim = false;
	bAimToggle = false;
	BrowserClip = NAME_None;
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->ResetOperative(true);
	FaceClear();
	SetLookAtCamera(false);
	ResetCameraSmoothing();
}

void AShowcasePlayerController::CmdToggleRoot() { if (auto* A = GetActions()) A->SetRoot(!A->IsRooted()); }
void AShowcasePlayerController::CmdToggleSilence() { if (auto* A = GetActions()) A->SetSilence(!A->IsSilenced()); }
void AShowcasePlayerController::CmdToggleDisarm() { if (auto* A = GetActions()) A->SetDisarm(!A->IsDisarmed()); }

void AShowcasePlayerController::CmdToggleStasis()
{
	AOperativeCharacter* O = GetOperative();
	if (!O) return;
	const bool bOn = !O->Actions->IsStasis();
	O->Actions->SetStasis(bOn);
	O->GetMesh()->bPauseAnims = bOn;
}

void AShowcasePlayerController::SetManualLocomotion(bool bOn, float AngleLeftDeg, float SpeedCmS)
{
	bManualLoco = bOn;
	ManualAngle = AngleLeftDeg;
	ManualSpeed = SpeedCmS;
}

void AShowcasePlayerController::SetManualAim(bool bOn, float YawLeftDeg, float PitchUpDeg)
{
	bManualAim = bOn;
	ManualAimYaw = YawLeftDeg;
	ManualAimPitch = PitchUpDeg;
	if (bOn) bAimToggle = true;
}

void AShowcasePlayerController::CycleFacingMode()
{
	if (auto* A = GetActions())
	{
		const EOperativeFacingMode M = A->GetFacingMode();
		A->SetFacingMode(M == EOperativeFacingMode::Aim ? EOperativeFacingMode::Movement : M == EOperativeFacingMode::Movement ? EOperativeFacingMode::Locked : EOperativeFacingMode::Aim);
	}
}

void AShowcasePlayerController::SetFacingMode(EOperativeFacingMode M) { if (auto* A = GetActions()) A->SetFacingMode(M); }

void AShowcasePlayerController::SetActionRate(float Rate)
{
	if (auto* A = GetActions()) A->SetActionRate(Rate);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->Actions->SetActionRate(Rate);
}

void AShowcasePlayerController::AdjustActionRate(float Delta)
{
	if (auto* A = GetActions()) SetActionRate(A->GetActionRate() + Delta);
}

void AShowcasePlayerController::SetLookAtCamera(bool b)
{
	bLookAtCamera = b;
	if (auto* A = GetActions())
	{
		if (!b) A->SetLookTarget(FVector::ZeroVector, false);
	}
}

// ------------------------------------------------------------------------------------------------ views and display

void AShowcasePlayerController::SetView(EShowcaseView V)
{
	View = V;
	switch (V)
	{
	case EShowcaseView::ThirdPerson: OrbitDistance = InstanceCount > 1 ? 900.f : 390.f; OrbitPitch = InstanceCount > 1 ? -24.f : -10.f; if (InstanceCount > 1) OrbitYaw = 15.f; break;
	case EShowcaseView::Front: OrbitDistance = 500.f; break;      // 500 cm at a 44 degree field of view: the whole body with margin (the side camera stays clear of the steps)
	case EShowcaseView::Side: OrbitDistance = 500.f; break;
	case EShowcaseView::TopDown: OrbitDistance = 1580.f; OrbitPitch = -55.f; OrbitYaw = 0.f; break;
	default: break;
	}
	if (V == EShowcaseView::ThirdPerson && OrbitYaw == 0.f) OrbitYaw = 200.f;
	if (AShowcaseRoom* R = GetRoom()) { R->SetFaceLighting(V == EShowcaseView::Face); R->SetWallsHiddenForView(V == EShowcaseView::TopDown); }
	if (V == EShowcaseView::Face) SetLookAtCamera(true);
	else if (bLookAtCamera) SetLookAtCamera(false);
	// the front, side, face and hands cameras follow the body facing: a cursor aim would chase itself, so these views aim straight ahead
	// (the aim sliders of the panel and RMB still work)
	bCursorAim = (V == EShowcaseView::ThirdPerson || V == EShowcaseView::TopDown);
	// the outline hull shows through the mouth opening at close range: the face view draws without it
	if (AOperativeCharacter* O = GetOperative()) O->SetOutlineSuppressed(V == EShowcaseView::Face);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->SetOutlineSuppressed(V == EShowcaseView::Face);
	bCameraSnap = false;
}

void AShowcasePlayerController::CycleView()
{
	SetView(static_cast<EShowcaseView>((static_cast<int32>(View) + 1) % 6));
}

void AShowcasePlayerController::SetOrbit(float Yaw, float Pitch, float Distance)
{
	OrbitYaw = Yaw;
	OrbitPitch = Pitch;
	OrbitDistance = Distance;
}

FString AShowcasePlayerController::GetViewName() const
{
	static const TCHAR* N[] = { TEXT("third person"), TEXT("front"), TEXT("side"), TEXT("top-down 55 deg"), TEXT("face close-up"), TEXT("hands / props"), TEXT("orbit") };
	return N[static_cast<int32>(View)];
}

FString AShowcasePlayerController::GetRenderModeName() const
{
	static const TCHAR* N[] = { TEXT("textured"), TEXT("normals"), TEXT("wireframe"), TEXT("clay mesh") };
	const AOperativeCharacter* O = GetOperative();
	return N[FMath::Clamp(O ? O->GetRenderMode() : 0, 0, 3)];
}

FString AShowcasePlayerController::GetFacingModeName() const
{
	if (const UOperativeActionComponent* A = GetActions())
	{
		switch (A->GetFacingMode())
		{
		case EOperativeFacingMode::Aim: return TEXT("aim");
		case EOperativeFacingMode::Movement: return TEXT("movement");
		default: return TEXT("locked");
		}
	}
	return TEXT("-");
}

void AShowcasePlayerController::CycleRenderMode()
{
	const AOperativeCharacter* O = GetOperative();
	SetRenderMode(((O ? O->GetRenderMode() : 0) + 1) % 4);
}

void AShowcasePlayerController::SetRenderMode(int32 M)
{
	if (AOperativeCharacter* O = GetOperative()) O->SetRenderMode(M);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->SetRenderMode(M);
}

void AShowcasePlayerController::CycleLOD()
{
	const AOperativeCharacter* O = GetOperative();
	SetLOD(((O ? O->GetForcedLOD() : 0) + 1) % 4);
}

void AShowcasePlayerController::SetLOD(int32 Lod)
{
	if (AOperativeCharacter* O = GetOperative()) O->SetForcedLOD(Lod);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->SetForcedLOD(Lod);
}

void AShowcasePlayerController::ToggleTeam()
{
	const AOperativeCharacter* O = GetOperative();
	SetTeam(O && O->GetTeam() == EOperativeTeam::A ? EOperativeTeam::B : EOperativeTeam::A);
}

void AShowcasePlayerController::SetTeam(EOperativeTeam T)
{
	if (AOperativeCharacter* O = GetOperative()) O->SetTeam(T);
	int32 I = 0;
	for (AOperativeCharacter* E : ExtraOperatives)
	{
		if (!E) continue;
		// the other instances alternate the teams so both variants are visible in the group
		E->SetTeam((I++ % 2 == 0) ? (T == EOperativeTeam::A ? EOperativeTeam::B : EOperativeTeam::A) : T);
	}
}

void AShowcasePlayerController::ToggleOutline()
{
	bOutline = !bOutline;
	if (AOperativeCharacter* O = GetOperative()) O->SetOutlineEnabled(bOutline);
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->SetOutlineEnabled(bOutline);
}

void AShowcasePlayerController::ToggleStudio()
{
	if (AShowcaseRoom* R = GetRoom()) R->SetStudioMode(!R->IsStudioMode());
}

bool AShowcasePlayerController::IsStudio() const
{
	const AShowcaseRoom* R = GetRoom();
	return R && R->IsStudioMode();
}

void AShowcasePlayerController::TogglePanel()
{
	bPanelVisible = !bPanelVisible;
	if (Panel.IsValid()) Panel->SetVisibility(bPanelVisible ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed);
}

void AShowcasePlayerController::ToggleInstances()
{
	SetInstances(InstanceCount > 1 ? 1 : 10);
}

void AShowcasePlayerController::SetInstances(int32 Count)
{
	Count = FMath::Clamp(Count, 1, 10);
	if (Count == InstanceCount) return;
	InstanceCount = Count;
	SpawnInstances(Count);
	if (View == EShowcaseView::ThirdPerson)
	{
		// the group stands east of the start: the camera looks east from the west side so it stays inside the room
		OrbitDistance = Count > 1 ? 900.f : 390.f;
		OrbitPitch = Count > 1 ? -24.f : -10.f;
		OrbitYaw = Count > 1 ? 15.f : 200.f;
	}
}

void AShowcasePlayerController::SpawnInstances(int32 Count)
{
	for (AOperativeCharacter* E : ExtraOperatives) if (E) E->Destroy();
	ExtraOperatives.Reset();
	if (Count <= 1) return;
	AOperativeCharacter* Main = GetOperative();
	if (!Main) return;
	const FVector Base = Main->GetActorLocation();
	static const FVector2D Grid[9] = { {450, -300}, {450, 0}, {450, 300}, {700, -300}, {700, 0}, {700, 300}, {950, -300}, {950, 0}, {950, 300} };
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	for (int32 I = 0; I < Count - 1 && I < 9; ++I)
	{
		const FVector Loc(Grid[I].X, Grid[I].Y, Base.Z);
		AOperativeCharacter* E = GetWorld()->SpawnActor<AOperativeCharacter>(AOperativeCharacter::StaticClass(), Loc, FRotator(0.f, 180.f + I * 17.f, 0.f), SP);
		if (!E) continue;
		E->bAutopilot = true;
		E->AutopilotSeed = 1000 + I * 37;
		E->SetTeam((I % 2 == 0) ? EOperativeTeam::B : EOperativeTeam::A);
		E->SetSpawnTransform(FTransform(FRotator(0.f, 180.f + I * 17.f, 0.f), Loc));
		E->SetForcedLOD(Main->GetForcedLOD());
		E->SetRenderMode(Main->GetRenderMode());
		E->SetOutlineEnabled(bOutline);
		E->SetOutlineSuppressed(View == EShowcaseView::Face);
		ExtraOperatives.Add(E);
	}
	SetTeam(Main->GetTeam());
}

void AShowcasePlayerController::ToggleTargetsPatrol()
{
	if (AShowcaseRoom* R = GetRoom()) R->SetTargetsPatrol(!R->GetTargetsPatrol());
}

void AShowcasePlayerController::SelectNextTarget()
{
	if (AShowcaseRoom* R = GetRoom()) R->SelectNextTarget();
}

void AShowcasePlayerController::MoveSelectedTargetToCursor()
{
	if (AShowcaseRoom* R = GetRoom())
	{
		FVector Loc, Dir;
		if (DeprojectMousePositionToWorld(Loc, Dir) && !FMath::IsNearlyZero(Dir.Z))
		{
			const float T = -Loc.Z / Dir.Z;
			if (T > 0.f) R->MoveSelectedTarget(Loc + Dir * T);
		}
	}
}

void AShowcasePlayerController::ToggleMotionViewerStation()
{
	AOperativeCharacter* O = GetOperative();
	AShowcaseRoom* R = GetRoom();
	if (!O || !R) return;
	bMotionViewerStation = !bMotionViewerStation;
	R->SetViewerBackdropShown(bMotionViewerStation);
	if (bMotionViewerStation)
	{
		StationReturnLocation = O->GetActorLocation();
		O->TeleportTo(R->GetViewerPedestal() + FVector(0.f, 0.f, 105.f), FRotator(0.f, 0.f, 0.f), false, true);
		O->GetCharacterMovement()->Velocity = FVector::ZeroVector;
		SetView(EShowcaseView::Front);
		bCameraSnap = true;
	}
	else
	{
		O->TeleportTo(StationReturnLocation, O->GetActorRotation(), false, true);
		if (auto* A = GetActions()) A->StopViewer();
		SetView(EShowcaseView::ThirdPerson);
	}
	if (Panel.IsValid()) Panel->NotifyViewerMode(bMotionViewerStation);
}

void AShowcasePlayerController::StartSequence()
{
	if (AShowcaseDirector* D = GetDirector())
	{
		if (D->IsSequenceRunning()) D->StopSequence();
		else D->StartSequence(false);
	}
}

// ------------------------------------------------------------------------------------------------ browser and face

bool AShowcasePlayerController::BrowserPlay(FName ClipId)
{
	UOperativeActionComponent* A = GetActions();
	if (!A) return false;
	BrowserClip = ClipId;
	const bool bOk = A->PlayClip(ClipId, BrowserRate, bBrowserLoop, 0.f);
	if (bOk) A->SetFacingMode(EOperativeFacingMode::Locked);
	return bOk;
}

void AShowcasePlayerController::BrowserStop()
{
	if (UOperativeActionComponent* A = GetActions())
	{
		if (A->IsViewerActive()) A->StopViewer();
	}
	BrowserClip = NAME_None;
}

void AShowcasePlayerController::BrowserSetRate(float R)
{
	BrowserRate = FMath::Clamp(R, 0.5f, 1.5f);
	SetActionRate(BrowserRate);
	if (UOperativeActionComponent* A = GetActions())
	{
		if (A->IsViewerActive())
		{
			// apply to the running viewer players through a restart at the current time
			const float T = A->GetBaseClipTime();
			if (!BrowserClip.IsNone()) A->PlayClip(BrowserClip, BrowserRate, bBrowserLoop, T);
		}
	}
}

void AShowcasePlayerController::FaceSetPreset(FName Preset)
{
	if (AOperativeCharacter* O = GetOperative()) O->Face->ApplyPreset(Preset);
}

void AShowcasePlayerController::FaceClear()
{
	if (AOperativeCharacter* O = GetOperative()) O->Face->ClearAll();
}

void AShowcasePlayerController::SequenceMove(const FVector& WorldDir, float Speed)
{
	SequenceMoveDir = WorldDir;
	SequenceMoveSpeed = Speed;
}

void AShowcasePlayerController::SequenceAim(const FVector& WorldPoint)
{
	SequenceAimPoint = WorldPoint;
}
