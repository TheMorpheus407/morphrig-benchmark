#include "ShowcasePlayerController.h"
#include "MorphRig.h"
#include "OperativeCharacter.h"
#include "OperativeStateComponent.h"
#include "ShowcaseDirector.h"
#include "ShowcaseRoom.h"
#include "SShowcasePanel.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "InputCoreTypes.h"
#include "Widgets/SWeakWidget.h"
#include "Widgets/SViewport.h"
#include "Framework/Application/SlateApplication.h"

AShowcasePlayerController::AShowcasePlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	PrimaryActorTick.bCanEverTick = true;
}

FString AShowcasePlayerController::HelpText()
{
	return TEXT(
		"MOVE  W A S D (camera relative)   L-Shift sprint   L-Ctrl walk   M strafe/travel mode\n"
		"AIM   mouse = aim point   wheel = aim height   RMB hold = aim stance   Tab lock next target   drag a target with LMB\n"
		"ACT   LMB fire   B burst   R reload   F melee (again = combo)   Space jump   Q dash (WASD dir)   E blink to cursor\n"
		"CAST  1 directional   2 ground   3 self   C hold = channel (release = finish)   G hold = charge (release = fire)\n"
		"      X = interrupt channel / cancel charge / cancel uplink   T deploy beacon   U uplink\n"
		"HIT   7 front  8 left  9 back  0 right      4 stun  5 sleep  6 knock-back  - knock-up  [ knock-down (front hit)  ] (back hit)\n"
		"LIFE  K death (front hit)   L death (back hit)   P respawn   Backspace reset   I wounded\n"
		"EMOTE Z greet   V victory   N defeat   Enter speech sample\n"
		"VIEW  Home top-down  End third person  PgUp front  PgDn side  Insert face  H head+shoulders  Delete orbit (RMB drag, wheel zoom)  F9 cycle\n"
		"SHOW  F1 help  F2 panel  F3 HUD  F4 skeleton  F5 team A/B  F6 outline  F7 LOD  F8 textured/wireframe/normals/clay\n"
		"      F10 team ring  O 1/10 instances  , . action rate  F11 deterministic sequence\n"
		"PANEL (F2) tabs: Help | Animations (search + play any of the 96 clips) | Face | Character | States\n"
		"CONSOLE  ~ then:  mr <command>   e.g.  mr view walk_fl   mr flag silence on   mr viseme AA 1   (docs/showcase_controls.md)");
}

void AShowcasePlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI Mode;
	Mode.SetHideCursorDuringCapture(false);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(Mode);
	if (GEngine && GEngine->GameViewport && IsLocalController())
	{
		Panel = SNew(SShowcasePanel).World(GetWorld());
		GEngine->GameViewport->AddViewportWidgetContent(SNew(SWeakWidget).PossiblyNullContent(Panel), 10);
	}
}

void AShowcasePlayerController::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Panel.IsValid() && GEngine && GEngine->GameViewport)
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(Panel.ToSharedRef());
	}
	Panel.Reset();
	Super::EndPlay(Reason);
}

void AShowcasePlayerController::SetPanelTab(const FString& Name)
{
	if (Panel.IsValid())
	{
		Panel->SetTabByName(Name);
	}
}

bool AShowcasePlayerController::CursorGroundPoint(double PlaneZ, FVector& Out, FVector* OutOrigin, FVector* OutDir) const
{
	FVector Origin, Dir;
	if (!DeprojectMousePositionToWorld(Origin, Dir))
	{
		return false;
	}
	if (OutOrigin)
	{
		*OutOrigin = Origin;
	}
	if (OutDir)
	{
		*OutDir = Dir;
	}
	if (FMath::Abs(Dir.Z) < 1.e-4)
	{
		return false;
	}
	const double T = (PlaneZ - Origin.Z) / Dir.Z;
	if (T <= 0.0)
	{
		return false;
	}
	Out = Origin + Dir * T;
	return true;
}

void AShowcasePlayerController::HandleHotkeys(AShowcaseDirector* D)
{
	struct FBinding { FKey Key; const TCHAR* Command; };
	static const FBinding Bindings[] = {
		{ EKeys::F1, TEXT("help toggle") }, { EKeys::F2, TEXT("panel toggle") }, { EKeys::F3, TEXT("hud toggle") }, { EKeys::F4, TEXT("skeleton toggle") },
		{ EKeys::F5, TEXT("team toggle") }, { EKeys::F6, TEXT("outline toggle") }, { EKeys::F7, TEXT("lod cycle") }, { EKeys::F8, TEXT("display cycle") },
		{ EKeys::F9, TEXT("cam cycle") }, { EKeys::F10, TEXT("ring toggle") }, { EKeys::F11, TEXT("sequence") },
		{ EKeys::Home, TEXT("cam top") }, { EKeys::End, TEXT("cam third") }, { EKeys::PageUp, TEXT("cam front") }, { EKeys::PageDown, TEXT("cam side") },
		{ EKeys::Insert, TEXT("cam face") }, { EKeys::H, TEXT("cam bust") }, { EKeys::Delete, TEXT("cam orbit") },
		{ EKeys::O, TEXT("instances toggle") }, { EKeys::M, TEXT("strafe toggle") }, { EKeys::I, TEXT("wounded toggle") },
		{ EKeys::SpaceBar, TEXT("jump") }, { EKeys::F, TEXT("melee") }, { EKeys::R, TEXT("reload") }, { EKeys::B, TEXT("burst") },
		{ EKeys::One, TEXT("cast directional") }, { EKeys::Two, TEXT("cast ground") }, { EKeys::Three, TEXT("cast self") },
		{ EKeys::Four, TEXT("stun 2") }, { EKeys::Five, TEXT("sleep 5") }, { EKeys::Six, TEXT("knockback f") },
		{ EKeys::Seven, TEXT("hit f") }, { EKeys::Eight, TEXT("hit l") }, { EKeys::Nine, TEXT("hit b") }, { EKeys::Zero, TEXT("hit r") },
		{ EKeys::Hyphen, TEXT("knockup") }, { EKeys::LeftBracket, TEXT("knockdown front") }, { EKeys::RightBracket, TEXT("knockdown back") },
		{ EKeys::K, TEXT("kill front") }, { EKeys::L, TEXT("kill back") }, { EKeys::P, TEXT("respawn") }, { EKeys::BackSpace, TEXT("reset") },
		{ EKeys::Z, TEXT("emote greet") }, { EKeys::V, TEXT("emote victory") }, { EKeys::N, TEXT("emote defeat") }, { EKeys::Enter, TEXT("speech") },
		{ EKeys::T, TEXT("deploy") }, { EKeys::U, TEXT("uplink start") }, { EKeys::Tab, TEXT("aimtarget cycle") },
	};
	for (const FBinding& B : Bindings)
	{
		if (JustPressed(B.Key))
		{
			D->Exec(B.Command);
		}
	}
	AOperativeCharacter* Ch = D->GetPrimary();
	UOperativeStateComponent* S = Ch ? Ch->StateComp.Get() : nullptr;
	if (!S)
	{
		return;
	}
	if (JustPressed(EKeys::C)) { D->Exec(TEXT("channel start")); }
	if (JustReleased(EKeys::C)) { D->Exec(TEXT("channel release")); }
	if (JustPressed(EKeys::G)) { D->Exec(TEXT("charge start")); }
	if (JustReleased(EKeys::G)) { D->Exec(TEXT("charge release")); }
	if (JustPressed(EKeys::X))
	{
		D->Exec(TEXT("channel interrupt"));
		D->Exec(TEXT("charge cancel"));
		D->Exec(TEXT("uplink cancel"));
	}
	if (JustPressed(EKeys::Comma)) { D->Exec(FString::Printf(TEXT("rate %.2f"), S->ActionRate - 0.25f)); }
	if (JustPressed(EKeys::Period)) { D->Exec(FString::Printf(TEXT("rate %.2f"), S->ActionRate + 0.25f)); }
	if (JustPressed(EKeys::Q))
	{
		float Dir = 0.f;
		const FVector Move = S->Input.MoveDir;
		if (!Move.IsNearlyZero())
		{
			const FVector Fwd = Ch->GetActorForwardVector(), Left = -Ch->GetActorRightVector();
			Dir = FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(Move, Left), FVector::DotProduct(Move, Fwd)));
		}
		D->Exec(FString::Printf(TEXT("dash %.0f"), Dir));
	}
	if (JustPressed(EKeys::E))
	{
		FVector P;
		if (CursorGroundPoint(Ch->GetActorLocation().Z - 90.0, P))
		{
			FVector Delta = P - Ch->GetActorLocation();
			Delta.Z = 0.0;
			Delta = Delta.GetClampedToMaxSize(600.0);
			const FVector Dest = Ch->GetActorLocation() + Delta;
			D->Exec(FString::Printf(TEXT("blink %.0f %.0f"), Dest.X, Dest.Y));
		}
	}
}

void AShowcasePlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	AShowcaseDirector* D = AShowcaseDirector::Get(this);
	AOperativeCharacter* Ch = D ? D->GetPrimary() : nullptr;
	if (!D || !Ch)
	{
		return;
	}
	UOperativeStateComponent* S = Ch->StateComp;
	AShowcaseRoom* Room = AShowcaseRoom::Get(GetWorld());
	FOpInput In;

	if (D->bScriptedInput)
	{
		In.MoveDir = D->ScriptMove;
		In.bSprint = D->bScriptSprint;
		In.bWalk = D->bScriptWalk;
		In.bAim = D->bScriptAim;
		In.SpeedOverride = D->ScriptSpeed;
		if (D->bScriptAimPoint)
		{
			In.bHasAimPoint = true;
			In.AimPoint = D->ScriptAimPoint;
		}
	}
	else
	{
		HandleHotkeys(D);
		// camera relative movement
		float CamYaw = 0.f;
		if (PlayerCameraManager)
		{
			CamYaw = (float)PlayerCameraManager->GetCameraRotation().Yaw;
		}
		const FRotator YawRot(0, CamYaw, 0);
		const FVector Fwd = YawRot.Vector();
		const FVector Right = FRotationMatrix(YawRot).GetUnitAxis(EAxis::Y);
		FVector Move = FVector::ZeroVector;
		if (IsInputKeyDown(EKeys::W)) { Move += Fwd; }
		if (IsInputKeyDown(EKeys::S)) { Move -= Fwd; }
		if (IsInputKeyDown(EKeys::D)) { Move += Right; }
		if (IsInputKeyDown(EKeys::A)) { Move -= Right; }
		In.MoveDir = Move.GetSafeNormal2D();
		In.bSprint = IsInputKeyDown(EKeys::LeftShift);
		In.bWalk = IsInputKeyDown(EKeys::LeftControl);
		In.SpeedOverride = D->ScriptSpeed;

		// mouse: aim point on the ground plane lifted by the aim height, target dragging, orbit camera
		const double FeetZ = Ch->GetActorLocation().Z - 90.0;
		FVector Ground, RayO, RayD;
		const bool bHaveGround = CursorGroundPoint(FeetZ, Ground, &RayO, &RayD);
		float MX = 0.f, MY = 0.f;
		GetMousePosition(MX, MY);
		const FVector2D Mouse(MX, MY);
		const bool bOrbit = D->CameraMode == EShowcaseCamera::Orbit;
		if (bOrbit && IsInputKeyDown(EKeys::RightMouseButton))
		{
			if (bOrbitDrag)
			{
				D->OrbitYaw += (float)(Mouse.X - LastMouse.X) * 0.35f;
				D->OrbitPitch = FMath::Clamp(D->OrbitPitch - (float)(Mouse.Y - LastMouse.Y) * 0.3f, -85.f, 40.f);
			}
			bOrbitDrag = true;
		}
		else
		{
			bOrbitDrag = false;
		}
		LastMouse = Mouse;
		const float Wheel = GetInputAnalogKeyState(EKeys::MouseWheelAxis);
		if (JustPressed(EKeys::MouseScrollUp) || JustPressed(EKeys::MouseScrollDown))
		{
			const float Step = JustPressed(EKeys::MouseScrollUp) ? 1.f : -1.f;
			if (bOrbit)
			{
				D->OrbitDistance = FMath::Clamp(D->OrbitDistance - Step * 40.f, 60.f, 1500.f);
			}
			else if (DragTarget != INDEX_NONE && Room)
			{
				FVector P = Room->GetAimTargetLocation(DragTarget);
				P.Z += Step * 15.f;
				Room->SetAimTargetLocation(DragTarget, P);
			}
			else
			{
				AimHeight = FMath::Clamp(AimHeight + Step * 20.f, -40.f, 420.f);
			}
		}
		(void)Wheel;
		// a click that only brings the keyboard focus back from the panel (search box) must not fire a shot
		bool bViewportFocused = true;
		if (FSlateApplication::IsInitialized() && GEngine && GEngine->GameViewport)
		{
			const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();
			bViewportFocused = !Focused.IsValid() || Focused == GEngine->GameViewport->GetGameViewportWidget();
		}
		const bool bRefocusClick = !bViewportHadFocus;
		bViewportHadFocus = bViewportFocused;
		if (JustPressed(EKeys::LeftMouseButton) && !bRefocusClick)
		{
			const int32 Hit = (Room && bHaveGround) ? Room->FindTargetAt(RayO, RayD) : INDEX_NONE;
			if (Hit != INDEX_NONE)
			{
				DragTarget = Hit;
				D->LockTarget(Hit);
			}
			else
			{
				D->Exec(TEXT("fire"));
			}
		}
		if (!IsInputKeyDown(EKeys::LeftMouseButton))
		{
			DragTarget = INDEX_NONE;
		}
		if (DragTarget != INDEX_NONE && Room && bHaveGround)
		{
			// drag on the horizontal plane through the target centre
			const FVector Cur = Room->GetAimTargetLocation(DragTarget);
			FVector OnPlane;
			if (CursorGroundPoint(Cur.Z, OnPlane))
			{
				Room->SetAimTargetLocation(DragTarget, FVector(OnPlane.X, OnPlane.Y, Cur.Z));
			}
		}
		In.bAim = IsInputKeyDown(EKeys::RightMouseButton) && !bOrbit;
		if (D->LockedTarget != INDEX_NONE && Room)
		{
			In.bHasAimPoint = true;
			In.AimPoint = Room->GetAimTargetLocation(D->LockedTarget);
			In.bAim = true;
		}
		else if (bHaveGround && !bOrbit && D->CameraMode != EShowcaseCamera::Face && D->CameraMode != EShowcaseCamera::Bust && D->CameraMode != EShowcaseCamera::Turntable)
		{
			In.bHasAimPoint = true;
			In.AimPoint = Ground + FVector(0, 0, AimHeight);
		}
	}
	if (D->bScriptedInput && D->LockedTarget != INDEX_NONE && Room)
	{
		In.bHasAimPoint = true;
		In.AimPoint = Room->GetAimTargetLocation(D->LockedTarget);
	}
	S->Input = In;
}
