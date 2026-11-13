#include "ShowcaseDirector.h"
#include "MorphRig.h"
#include "MorphRigData.h"
#include "OperativeCharacter.h"
#include "OperativeStateComponent.h"
#include "ShowcaseRoom.h"
#include "ShowcaseFX.h"
#include "ShowcasePlayerController.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformFileManager.h"
#include "HighResScreenshot.h"
#include "ImageWriteQueue.h"
#include "ImageWriteTask.h"
#include "ImagePixelData.h"
#include "ImageUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "RenderTimer.h"
#include "RHI.h"
#include "DynamicRHI.h"
#include "Slate/SceneViewport.h"
#include "UnrealClient.h"
#include "Widgets/SViewport.h"

namespace
{
	/** Deterministic showcase sequence: exercises the major combined states. Times are game seconds. */
	const TCHAR* GSequenceScript = TEXT(R"SEQ(
# --- setup
hud on
panel off
instances 1
reset
cam third
log SEQUENCE begin: idle variants
wait 2.0
# --- strafing: eight directions with independent facing (aim point fixed)
cam top
aim on
aimat 900 0 150
log SEQUENCE eight-direction walk with independent facing
walk on
move 1 0 1.3
move 1 1 1.3
move 0 1 1.3
move -1 1 1.3
move -1 0 1.3
move -1 -1 1.3
move 0 -1 1.3
move 1 -1 1.3
walk off
log SEQUENCE eight-direction run with independent facing
move 1 0 1.1
move 1 1 1.1
move 0 1 1.1
move -1 1 1.1
move -1 0 1.1
move -1 -1 1.1
move 0 -1 1.1
move 1 -1 1.1
move stop
wait 0.6
# --- moving ranged attacks and directional cast with upper-body layering
log SEQUENCE moving ranged attacks, burst and directional cast (upper body layer + aim)
move 0 1
wait 0.7
fire
wait 0.7
burst
wait 0.9
move 0 -1
wait 0.6
aimat 700 500 260
cast directional
wait 1.2
aimat 900 -300 40
fire
wait 0.6
move stop
wait 0.6
aim off
aimclear
# --- aim grid: nine calibrated samples
log SEQUENCE aim grid: yaw -60/0/+60 x pitch -35/0/+35 on the upper body, feet planted
goto spawn
cam front
move stop
aim on
aimat 500 0 132
wait 0.8
aimat 265 -424 132
wait 0.8
aimat 265 -424 455
wait 0.8
aimat 500 0 455
wait 0.8
aimat 265 424 455
wait 0.8
aimat 265 424 132
wait 0.8
aimat 265 424 -190
wait 0.8
aimat 500 0 -190
wait 0.8
aimat 265 -424 -190
wait 0.8
aimat 500 0 132
wait 0.5
aim off
aimclear
wait 0.4
# --- travel mode: start, sprint, stop, pivot, turns
log SEQUENCE travel mode: start, sprint, stop, pivot, turn in place
goto -1250 150
strafe off
cam third
wait 0.5
move 1 0 1.5
sprint on
move 1 0 1.3
sprint off
move stop
wait 1.0
move 1 0 1.2
move -1 -0.2 1.5
move 1 -0.2 1.5
move stop
wait 0.9
turn l
wait 0.9
turn r
wait 0.9
strafe on
# --- air
log SEQUENCE jump, fall and landings
goto spawn
cam side
wait 0.4
jump
wait 1.6
move 1 0
wait 0.9
jump
wait 1.3
move stop
wait 0.5
drop
wait 2.4
# --- dash (root motion drives the capsule) and blink (teleport is an event)
log SEQUENCE dashes with root motion and blink
cam top
goto spawn
wait 0.3
dash f
wait 0.7
dash b
wait 0.7
dash l
wait 0.7
dash r
wait 0.8
blink 400 300
wait 1.2
blink 0 0
wait 1.2
# --- melee combo with hit windows
log SEQUENCE melee combo with hit windows
cam third
melee
wait 0.5
melee
wait 0.8
melee
wait 1.6
melee
wait 1.2
# --- reload: complete, then cancelled
log SEQUENCE reload while walking, then a cancelled reload
cam third
walk on
move 0 1
wait 0.8
reload
wait 2.6
move stop
walk off
wait 0.5
reload
wait 0.35
dash b
wait 1.0
# --- charge: early release, full release, cancel
log SEQUENCE charge released early, released full, cancelled
aim on
aimat 800 200 150
charge start
wait 0.35
charge release
wait 1.1
charge start
wait 2.4
charge release
wait 1.1
charge start
wait 1.0
charge cancel
wait 0.9
aim off
# --- channel: interrupted midway, then completed
log SEQUENCE channel interrupted midway, then completed normally
aimat 800 200 120
channel start
wait 1.3
channel interrupt
wait 0.9
channel start
wait 2.2
channel release
wait 1.0
aimclear
# --- ground / self casts, deploy, uplink
log SEQUENCE ground cast, self cast, deploy at the prop station, uplink cancel and completion
aimat 300 250 0
cast ground
wait 1.5
cast self
wait 1.3
aimclear
goto station
cam side
wait 0.4
deploy
wait 2.0
uplink start
wait 1.4
hit f
wait 1.0
uplink start
wait 5.6
cam top
wait 2.2
# --- hits while moving, disables
log SEQUENCE additive hits while moving
goto 0 -900
cam third
move 0 1
wait 0.7
hit f
wait 0.6
hit l
wait 0.6
hit b
wait 0.6
hit r
wait 0.7
move stop
wait 0.6
log SEQUENCE stun, sleep (woken by damage), knock-back, knock-up, knock-downs and get-ups
cam front
stun 1.2
wait 2.8
sleep 6
wait 3.0
hit f
wait 1.8
knockback 0
wait 1.3
knockup
wait 5.2
knockdown front
wait 4.6
knockdown back
wait 4.6
# --- death during cast, respawn, death during jump
log SEQUENCE death overrides a cast, respawn, death during a jump, respawn
cam side
cast ground
wait 0.3
kill front
wait 0.5
kill back
wait 2.6
respawn
wait 3.0
jump
wait 0.45
kill back
wait 3.2
respawn
wait 3.0
# --- soft flags
log SEQUENCE status flags: root, silence, disarm, stasis, fear, charm, taunt
cam top
flag root on
move 1 0
wait 0.5
fire
wait 0.9
move stop
flag root off
flag silence on
cast self
channel start
wait 0.5
flag silence off
flag disarm on
melee
fire
wait 0.5
flag disarm off
move 0 1
wait 0.8
flag stasis on
wait 1.0
flag stasis off
wait 0.6
move stop
flag fear on 300 0
wait 1.6
flag fear off
flag charm on 300 0
wait 1.8
flag charm off
flag taunt on 0 400
wait 1.6
flag taunt off
# --- wounded presentation
log SEQUENCE wounded presentation
cam third
wounded on
wait 1.5
move 0 1 2.0
wait 2.4
wounded off
# --- slope and steps with ground adaptation
log SEQUENCE ramp (20 deg) and steps (20 cm) with ground adaptation, walking
goto ramp
cam side
wait 0.4
walk on
move 1 0 5.1
move 0 1 2.0
move -1 0 5.6
walk off
log SEQUENCE ramp and steps, running
goto ramp
wait 0.3
move 1 0 1.9
move 0 1 0.75
move -1 0 1.7
move stop
wait 0.6
# --- action rate
log SEQUENCE action rate 0.5x and 1.5x
goto spawn
cam third
rate 0.5
melee
wait 2.0
fire
wait 1.0
rate 1.5
melee
wait 0.4
melee
wait 0.9
reload
wait 1.6
rate 1.0
# --- emotes and speech
log SEQUENCE greet, victory, defeat, speech sample
cam front
emote greet
wait 2.3
emote victory
wait 3.3
emote defeat
wait 3.1
cam bust
emote dialogue
waitidle 60
wait 0.4
cam third
wait 0.6
log SEQUENCE end
)SEQ");

	FString JsonEscape(const FString& In)
	{
		return In.ReplaceCharWithEscapedChar();
	}
}

AShowcaseDirector::AShowcaseDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

AShowcaseDirector* AShowcaseDirector::Get(const UObject* WorldContext)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World)
	{
		return nullptr;
	}
	TActorIterator<AShowcaseDirector> It(World);
	if (It)
	{
		return *It;
	}
	return nullptr;
}

AOperativeCharacter* AShowcaseDirector::GetPrimary() const
{
	return Instances.Num() > 0 ? Instances[0].Get() : nullptr;
}

void AShowcaseDirector::BeginPlay()
{
	Super::BeginPlay();
	UWorld* W = GetWorld();
	TraceFile = FPaths::ProjectSavedDir() / TEXT("MorphRigTrace.log");
	FString Override;
	if (FParse::Value(FCommandLine::Get(), TEXT("MorphTrace="), Override))
	{
		TraceFile = Override;
	}
	FFileHelper::SaveStringToFile(FString::Printf(TEXT("# MORPHRIG showcase trace (%s)\n"), *FDateTime::Now().ToString()), *TraceFile);
	TraceHandle = UOperativeStateComponent::OnTrace.AddUObject(this, &AShowcaseDirector::OnStateTrace);
	BeginFrameHandle = FCoreDelegates::OnBeginFrame.AddUObject(this, &AShowcaseDirector::ApplyPendingTimeStep);

	const FMorphRigData& Data = FMorphRigData::Get();
	TraceLine(FString::Printf(TEXT("DATA clips=%d bones=%d morphs=%d placeholder=%d %s"), Data.Clips.Num(), Data.Bones.Num(), Data.Morphs.Num(), Data.bPlaceholder ? 1 : 0, *Data.Error));
	for (const FString& Missing : Data.MissingControllerNames())
	{
		TraceLine(FString::Printf(TEXT("DATA ERROR the controller needs %s, which skeleton_and_sockets.json does not list"), *Missing));
	}
	if (Data.DisabledMorphs.Num() > 0)
	{
		TraceLine(FString::Printf(TEXT("DATA WARNING %d of %d morph targets failed the import sanity check and are not driven"), Data.DisabledMorphs.Num(), Data.Morphs.Num()));
	}

	Room = W->SpawnActor<AShowcaseRoom>();
	AShowcaseFX::Get(W);
	Camera = W->SpawnActor<ACameraActor>(CamPos, CamRot);
	if (Camera)
	{
		UCameraComponent* CC = Camera->GetCameraComponent();
		CC->bConstrainAspectRatio = false;
		CC->PostProcessSettings.bOverride_MotionBlurAmount = true;
		CC->PostProcessSettings.MotionBlurAmount = 0.f;
		CC->PostProcessSettings.bOverride_BloomIntensity = true;
		CC->PostProcessSettings.BloomIntensity = 0.35f;
		CC->PostProcessSettings.bOverride_VignetteIntensity = true;
		CC->PostProcessSettings.VignetteIntensity = 0.f;
		CC->PostProcessSettings.bOverride_AmbientOcclusionIntensity = true;
		CC->PostProcessSettings.AmbientOcclusionIntensity = 0.6f;
	}
	if (GEngine)
	{
		GEngine->bEnableOnScreenDebugMessages = false;   // keep engine warnings out of captures (they stay in the log)
	}
	int32 Count = 1;
	FParse::Value(FCommandLine::Get(), TEXT("MorphInstances="), Count);
	SpawnInstances(FMath::Clamp(Count, 1, 10));
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		PC->SetViewTarget(Camera);
	}

	IConsoleManager::Get().RegisterConsoleCommand(TEXT("mr"), TEXT("MORPHRIG showcase command, e.g. `mr melee`, `mr view walk_fl`, `mr help`"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AShowcaseDirector* D = AShowcaseDirector::Get(World))
			{
				D->Exec(FString::Join(Args, TEXT(" ")));
			}
		}), ECVF_Default);

	// ---- command line automation
	const TCHAR* Cmd = FCommandLine::Get();
	bQuitWhenScriptDone = FParse::Param(Cmd, TEXT("MorphQuit"));
	FString Value;
	CaptureDirDefault = FPaths::ProjectSavedDir() / TEXT("Capture");
	FParse::Value(Cmd, TEXT("MorphCaptureDir="), CaptureDirDefault);
	float FixedFps = 0.f;
	if (FParse::Value(Cmd, TEXT("MorphFixedFps="), FixedFps) && FixedFps > 0.f)
	{
		// deterministic stepping without frame capture (fast verification runs)
		FApp::SetFixedDeltaTime(1.0 / FixedFps);
		FApp::SetUseFixedTimeStep(true);
		TraceLine(FString::Printf(TEXT("FIXED TIME STEP %.0f fps"), FixedFps));
	}
	if (FParse::Value(Cmd, TEXT("MorphCapture="), Value))
	{
		float Fps = 30.f;
		FParse::Value(Cmd, TEXT("MorphFPS="), Fps);
		StartCapture(Value, Fps);
	}
	if (FParse::Value(Cmd, TEXT("MorphScript="), Value))
	{
		RunScriptFile(Value);
	}
	else if (FParse::Param(Cmd, TEXT("MorphSequence")))
	{
		StartSequence();
	}
	if (FParse::Value(Cmd, TEXT("MorphExec="), Value, false))
	{
		TArray<FString> Parts;
		Value.ParseIntoArray(Parts, TEXT(";"));
		for (const FString& P : Parts)
		{
			Exec(P.TrimStartAndEnd());
		}
	}
}

void AShowcaseDirector::EndPlay(const EEndPlayReason::Type Reason)
{
	if (ScreenshotHandle.IsValid())
	{
		UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle);
		ScreenshotHandle.Reset();
	}
	StopCapture();
	ApplyPendingTimeStep();
	FCoreDelegates::OnBeginFrame.Remove(BeginFrameHandle);
	UOperativeStateComponent::OnTrace.Remove(TraceHandle);
	IConsoleManager::Get().UnregisterConsoleObject(TEXT("mr"), false);
	Super::EndPlay(Reason);
}

void AShowcaseDirector::TraceLine(const FString& Line)
{
	const FString Full = FString::Printf(TEXT("[%9.3f] %s"), ShowTime, *Line);
	UE_LOG(LogMorphRig, Display, TEXT("TRACE %s"), *Full);
	FFileHelper::SaveStringToFile(Full + TEXT("\n"), *TraceFile, FFileHelper::EEncodingOptions::AutoDetect, &IFileManager::Get(), FILEWRITE_Append);
	RecentTrace.Add(Line);
	if (RecentTrace.Num() > 12)
	{
		RecentTrace.RemoveAt(0, RecentTrace.Num() - 12);
	}
}

void AShowcaseDirector::OnStateTrace(const AActor* Actor, const FString& Line)
{
	const AOperativeCharacter* Ch = Cast<AOperativeCharacter>(Actor);
	if (!Ch || Ch->GetWorld() != GetWorld())
	{
		return;
	}
	if (Ch->InstanceIndex != 0)
	{
		return;   // the trace follows the controlled Operative; the autopilot instances stay quiet
	}
	// strip the component's local time stamp, the director adds the showcase clock
	FString Body = Line;
	int32 Close = INDEX_NONE;
	if (Body.FindChar(TEXT(']'), Close))
	{
		Body = Body.Mid(Close + 2);
	}
	TraceLine(Body);
}

// ================================================================================================ instances
void AShowcaseDirector::SpawnInstances(int32 Count)
{
	UWorld* W = GetWorld();
	const FVector Centers[3] = { FVector(-900, -950, 0), FVector(-100, -1050, 0), FVector(-1050, 60, 0) };
	while (Instances.Num() < Count)
	{
		const int32 Index = Instances.Num();
		FVector Loc = Room ? Room->SpawnPoint : FVector(0, 0, 92);
		float Yaw = 0.f;
		if (Index > 0)
		{
			const int32 Group = (Index - 1) % 3;
			const float Angle = (Index - 1) * 2.1f;
			Loc = Centers[Group] + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0) * (240.f + 45.f * ((Index - 1) / 3)) + FVector(0, 0, 92);
			Yaw = FMath::RadiansToDegrees(Angle) + 180.f;
		}
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		const FTransform Xf(FRotator(0, Yaw, 0), Loc);
		AOperativeCharacter* Ch = W->SpawnActorDeferred<AOperativeCharacter>(AOperativeCharacter::StaticClass(), Xf, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
		if (!Ch)
		{
			break;
		}
		Ch->InstanceIndex = Index;
		Ch->ViewerLocation = Room ? Room->ViewerPoint : Loc;
		if (Index > 0)
		{
			Ch->bAutopilot = true;
			Ch->AutopilotCenter = Centers[(Index - 1) % 3];
		}
		UGameplayStatics::FinishSpawningActor(Ch, Xf);
		// per frame order: director (script, clock) -> player controller (intent) -> state component -> movement -> pose
		Ch->StateComp->AddTickPrerequisiteActor(this);
		if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
		{
			Ch->StateComp->AddTickPrerequisiteActor(PC);
			PC->AddTickPrerequisiteActor(this);
		}
		if (Index > 0)
		{
			Ch->SetTeam(Index % 2);
		}
		Instances.Add(Ch);
	}
	while (Instances.Num() > Count)
	{
		if (AOperativeCharacter* Ch = Instances.Pop())
		{
			Ch->OnRespawned();
			Ch->Destroy();
		}
	}
}

void AShowcaseDirector::SetInstanceCount(int32 Count)
{
	SpawnInstances(FMath::Clamp(Count, 1, 10));
	Selected = 0;
	TraceLine(FString::Printf(TEXT("INSTANCES %d"), Instances.Num()));
}

// ================================================================================================ camera
FString AShowcaseDirector::GetCameraName() const
{
	switch (CameraMode)
	{
	case EShowcaseCamera::TopDown: return TEXT("top-down 55 deg");
	case EShowcaseCamera::ThirdPerson: return TEXT("third person");
	case EShowcaseCamera::Front: return TEXT("front full body");
	case EShowcaseCamera::Side: return TEXT("side full body");
	case EShowcaseCamera::Face: return TEXT("face close-up");
	case EShowcaseCamera::Orbit: return TEXT("free orbit");
	case EShowcaseCamera::Turntable: return TEXT("turntable");
	case EShowcaseCamera::Bust: return TEXT("head and shoulders");
	}
	return TEXT("?");
}

FVector AShowcaseDirector::GetCameraLocation() const
{
	return CamPos;
}

void AShowcaseDirector::SetCamera(EShowcaseCamera Mode)
{
	CameraMode = Mode;
	bCamSnap = true;
	if (Mode == EShowcaseCamera::Turntable)
	{
		TurntableYaw = 0.f;
	}
}

void AShowcaseDirector::UpdateCamera(float Dt)
{
	AOperativeCharacter* Ch = GetPrimary();
	if (!Ch || !Camera)
	{
		return;
	}
	const FVector Center = Ch->GetActorLocation();
	const float ActorYaw = (float)Ch->GetActorRotation().Yaw;
	if (bCamSnap)
	{
		InspectYaw = ActorYaw;
	}
	FVector Target = Center;
	FRotator Rot = CamRot;
	float Dist = 400.f, Fov = 50.f, Follow = 8.f;
	switch (CameraMode)
	{
	case EShowcaseCamera::TopDown:
		Rot = FRotator(-55.f, 0.f, 0.f);
		Dist = TopDownDistance;
		Target = Center - FVector(0, 0, 30);
		Fov = 50.f;
		Follow = 6.f;
		break;
	case EShowcaseCamera::ThirdPerson:
		Rot = FRotator(-12.f, bCamSnap ? ActorYaw : FMath::FixedTurn((float)CamRot.Yaw, ActorYaw, 200.f * Dt), 0.f);
		Dist = 330.f;
		Target = Center + FVector(0, 0, 25);
		Fov = 60.f;
		break;
	case EShowcaseCamera::Front:
		// inspection cameras keep a fixed world direction (so turns and travel can be judged) and follow the position
		Rot = FRotator(-4.f, InspectYaw + 180.f, 0.f);
		Dist = 520.f;
		Target = Center + FVector(0, 0, 5);
		Fov = 40.f;
		break;
	case EShowcaseCamera::Side:
		Rot = FRotator(-4.f, InspectYaw + 90.f, 0.f);
		Dist = 560.f;
		Target = Center + FVector(0, 0, 5);
		Fov = 40.f;
		break;
	case EShowcaseCamera::Face:
	case EShowcaseCamera::Bust:
	{
		// close-ups: follow the head joint (position only, lightly damped) and stay in front of the body, whatever the
		// aim / strafe facing is. Face: chin to hair top with margin (about 35 cm of height in view at 16:9);
		// bust: head, shoulders and chest (about 68 cm) so that hand gestures at chest height stay in the picture.
		const bool bBust = CameraMode == EShowcaseCamera::Bust;
		const FVector Want = Ch->GetMesh()->GetSocketLocation(TEXT("head")) + FVector(0, 0, bBust ? -7.f : 8.f);
		const float WantYaw = ActorYaw + 180.f;
		if (bCamSnap)
		{
			CloseTarget = Want;
			CloseYaw = WantYaw;
		}
		else
		{
			CloseTarget = FMath::VInterpTo(CloseTarget, Want, Dt, 6.f);
			CloseYaw += FRotator::NormalizeAxis(WantYaw - CloseYaw) * FMath::Clamp(Dt * 5.f, 0.f, 1.f);
		}
		Rot = FRotator(bBust ? -2.f : 0.f, CloseYaw, 0.f);
		Dist = bBust ? BustDistance : FaceDistance;
		Target = CloseTarget;
		Fov = 30.f;
		Follow = 1000.f;   // the target is already damped
		break;
	}
	case EShowcaseCamera::Orbit:
		Rot = FRotator(OrbitPitch, OrbitYaw, 0.f);
		Dist = OrbitDistance;
		Target = Center + FVector(0, 0, 10);
		Fov = 50.f;
		Follow = 14.f;
		break;
	case EShowcaseCamera::Turntable:
		TurntableYaw += TurntableSpeed * Dt;
		Rot = FRotator(-4.f, ActorYaw + 180.f + TurntableYaw, 0.f);
		Dist = 540.f;   // 180 cm character with margin at 16:9 (horizontal FOV 40 degrees -> about 220 cm of height in view)
		Target = Center + FVector(0, 0, 0);
		Fov = 40.f;
		Follow = 1000.f;
		break;
	}
	// the close-ups use a softer key light (lighter, wider penumbra) so that hair, brow and nose shadows stay clean
	// 0 = room key (gameplay views), 1 = close-up key, 2 = inspection key (front / side / turntable)
	int32 KeyLook = 0;
	if (CameraMode == EShowcaseCamera::Face || CameraMode == EShowcaseCamera::Bust)
	{
		KeyLook = 1;
	}
	else if (CameraMode == EShowcaseCamera::Front || CameraMode == EShowcaseCamera::Side || CameraMode == EShowcaseCamera::Turntable)
	{
		KeyLook = 2;
	}
	if (Room)
	{
		if (KeyLook != AppliedKeyLook)
		{
			AppliedKeyLook = KeyLook;
			AppliedKeyYaw = 1.e6f;
			Room->SetKeyShadow(KeyLook == 1 ? CloseShadowAmount : KeyShadowAmount, KeyLook == 1 ? CloseSourceAngle : KeySourceAngle);
			if (!KeyLook)
			{
				Room->ResetKeyDirection();
			}
		}
		if (KeyLook)
		{
			// the room key lights the character from behind in its default facing; seen from the front that leaves the face
			// in the fill with a ragged terminator across forehead and cheeks. In the inspection views and close-ups the
			// key therefore follows the view (three-quarter front, from above).
			const float KeyYaw = (float)Rot.Yaw + (KeyLook == 1 ? CloseKeyYawOffset : InspectKeyYawOffset);
			if (FMath::Abs(FRotator::NormalizeAxis(KeyYaw - AppliedKeyYaw)) > 0.5f)
			{
				AppliedKeyYaw = KeyYaw;
				Room->SetKeyDirection(FRotator(KeyLook == 1 ? -CloseKeyPitch : -InspectKeyPitch, KeyYaw, 0.f), KeyLook == 1 ? CloseKeyScale : InspectKeyScale);
			}
		}
	}
	const FVector WantPos = Target - Rot.Vector() * Dist;
	if (bCamSnap)
	{
		CamPos = WantPos;
		CamRot = Rot;
		CamFov = Fov;
		bCamSnap = false;
	}
	else
	{
		CamPos = FMath::VInterpTo(CamPos, WantPos, Dt, Follow);
		CamRot = Rot;
		CamFov = FMath::FInterpTo(CamFov, Fov, Dt, 8.f);
	}
	Camera->SetActorLocationAndRotation(CamPos, CamRot);
	Camera->GetCameraComponent()->SetFieldOfView(CamFov);
	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (PC->GetViewTarget() != Camera)
		{
			PC->SetViewTarget(Camera);
		}
		FVector2D A, B;
		if (PC->ProjectWorldLocationToScreen(Center - FVector(0, 0, 90), A) && PC->ProjectWorldLocationToScreen(Center + FVector(0, 0, 90), B))
		{
			ProjectedHeightPx = (float)FVector2D::Distance(A, B);
		}
	}
	Ch->StateComp->CameraLocation = CamPos;
}

void AShowcaseDirector::LockTarget(int32 Index)
{
	LockedTarget = Room && Index >= 0 && Index < Room->NumTargets() ? Index : INDEX_NONE;
	if (Room)
	{
		Room->HighlightTarget(LockedTarget);
	}
	TraceLine(LockedTarget == INDEX_NONE ? FString(TEXT("AIM target lock released")) : FString::Printf(TEXT("AIM locked on target %d"), LockedTarget));
}

// ================================================================================================ tick
void AShowcaseDirector::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	ShowTime += DeltaTime;
	UpdateScript(DeltaTime);
	if (ScriptMoveTime > 0.f)
	{
		ScriptMoveTime -= DeltaTime;
		if (ScriptMoveTime <= 0.f)
		{
			ScriptMove = FVector::ZeroVector;
		}
	}
	CaptionTime = FMath::Max(0.f, CaptionTime - DeltaTime);
	UpdateCamera(DeltaTime);
	UpdateCapture();
	if (AutoShotInterval > 0.f && !bCapturing && ShowTime >= NextAutoShot)
	{
		NextAutoShot = ShowTime + AutoShotInterval;
		FScreenshotRequest::RequestScreenshot(AutoShotDir / FString::Printf(TEXT("auto_%04d_t%07.2f.png"), AutoShotIndex++, ShowTime), false, false);
	}
	UpdateBenchmark(DeltaTime);
}

// ================================================================================================ scripts
bool AShowcaseDirector::RunScriptFile(const FString& Path)
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		TraceLine(FString::Printf(TEXT("SCRIPT cannot read %s"), *Path));
		return false;
	}
	RunScriptText(Text, FPaths::GetCleanFilename(Path));
	return true;
}

void AShowcaseDirector::RunScriptText(const FString& Text, const FString& Name)
{
	ScriptLines.Reset();
	TArray<FString> Lines;
	Text.ParseIntoArrayLines(Lines, true);
	for (FString L : Lines)
	{
		L.TrimStartAndEndInline();
		if (L.IsEmpty() || L.StartsWith(TEXT("#")))
		{
			continue;
		}
		FScriptLine SL;
		SL.Command = L;
		ScriptLines.Add(SL);
	}
	ScriptIndex = 0;
	ScriptClock = 0.0;
	ScriptWaitUntil = 0.0;
	ScriptName = Name;
	bScriptedInput = true;
	ScriptMove = FVector::ZeroVector;
	bScriptAim = false;
	bScriptAimPoint = false;
	bScriptSprint = bScriptWalk = false;
	ScriptSpeed = -1.f;
	TraceLine(FString::Printf(TEXT("SCRIPT %s started (%d commands)"), *Name, ScriptLines.Num()));
}

void AShowcaseDirector::StartSequence()
{
	RunScriptText(GSequenceScript, TEXT("deterministic showcase sequence"));
}

FString AShowcaseDirector::GetScriptStatus() const
{
	if (!IsScriptRunning())
	{
		return FString();
	}
	return FString::Printf(TEXT("%s  %d/%d  t=%.1fs"), *ScriptName, ScriptIndex, ScriptLines.Num(), ScriptClock);
}

void AShowcaseDirector::UpdateScript(float Dt)
{
	if (!IsScriptRunning())
	{
		return;
	}
	ScriptClock += Dt;
	if (bScriptWaitIdle)
	{
		// `waitidle [timeout]`: block until the controlled Operative is back in plain locomotion
		const AOperativeCharacter* Ch = GetPrimary();
		const bool bIdle = Ch && Ch->StateComp->GetState() == EOpState::Locomotion && !Ch->StateComp->GetBaseClip().IsValid() && !Ch->StateComp->GetUpperClip().IsValid();
		if (!bIdle && ScriptClock < ScriptWaitIdleUntil)
		{
			return;
		}
		bScriptWaitIdle = false;
	}
	if (bScriptTimedMove && ScriptClock >= ScriptWaitUntil)
	{
		// the timed move ends exactly when the script continues (the next command may start another move in this tick)
		bScriptTimedMove = false;
		ScriptMove = FVector::ZeroVector;
		ScriptMoveTime = 0.f;
	}
	while (ScriptIndex < ScriptLines.Num() && ScriptClock >= ScriptWaitUntil && !bScriptWaitIdle)
	{
		const FString Cmd = ScriptLines[ScriptIndex++].Command;
		TArray<FString> A;
		Cmd.ParseIntoArrayWS(A);
		if (A.Num() >= 2 && A[0] == TEXT("wait"))
		{
			ScriptWaitUntil = ScriptClock + FCString::Atof(*A[1]);
			continue;
		}
		if (A.Num() >= 1 && A[0] == TEXT("waitidle"))
		{
			bScriptWaitIdle = true;
			ScriptWaitIdleUntil = ScriptClock + (A.Num() >= 2 ? FCString::Atof(*A[1]) : 30.0);
			ScriptWaitUntil = ScriptClock + 0.05;   // let the previous command take effect first
			continue;
		}
		Exec(Cmd);
		if (A.Num() >= 2 && A[0] == TEXT("shot"))
		{
			// a screenshot shows the frame in which it was requested: let that frame render before the next command
			ScriptWaitUntil = ScriptClock + 1.e-4;
		}
		if (A.Num() >= 4 && A[0] == TEXT("move"))
		{
			// timed move commands block the script for their duration; the script, not a countdown, ends them
			ScriptWaitUntil = ScriptClock + FCString::Atof(*A[3]);
			bScriptTimedMove = true;
			ScriptMoveTime = 0.f;
		}
	}
	if (ScriptIndex >= ScriptLines.Num() && ScriptClock >= ScriptWaitUntil)
	{
		TraceLine(FString::Printf(TEXT("SCRIPT %s finished at t=%.3f"), *ScriptName, ScriptClock));
		ScriptLines.Reset();
		bScriptedInput = false;
		ScriptMove = FVector::ZeroVector;
		if (bQuitWhenScriptDone)
		{
			StopCapture();
			if (FHighResScreenshotConfig* Cfg = &GetHighResScreenshotConfig())
			{
				if (Cfg->ImageWriteQueue)
				{
					Cfg->ImageWriteQueue->CreateFence().Wait();
				}
			}
			FPlatformMisc::RequestExit(false);
		}
	}
}

// ================================================================================================ capture
void AShowcaseDirector::ApplyPendingTimeStep()
{
	// FApp time settings changed from inside an actor tick are reverted by the engine's per-task time context
	// (UE 5.8), so the switch is applied here, between frames.
	if (PendingFixedStep == 1)
	{
		FApp::SetFixedDeltaTime(1.0 / CaptureFps);
		FApp::SetUseFixedTimeStep(true);
		if (bCapturePending)
		{
			bCapturePending = false;
			bCapturing = true;
		}
	}
	else if (PendingFixedStep == 0)
	{
		FApp::SetUseFixedTimeStep(false);
	}
	PendingFixedStep = -1;
}

void AShowcaseDirector::StartCapture(const FString& Dir, float Fps)
{
	CaptureDir = Dir;
	CaptureFps = FMath::Clamp(Fps, 1.f, 240.f);
	CaptureFrame = 0;
	bCapturing = false;
	bCapturePending = true;
	PendingFixedStep = 1;
	IFileManager::Get().MakeDirectory(*CaptureDir, true);
	if (!ScreenshotHandle.IsValid())
	{
		// with this delegate bound the engine does not compress and write the frame on the game thread itself
		ScreenshotHandle = UGameViewportClient::OnScreenshotCaptured().AddUObject(this, &AShowcaseDirector::OnCaptureFrame);
	}
	TraceLine(FString::Printf(TEXT("CAPTURE requested dir=%s fps=%.0f (fixed time step from the next frame)"), *CaptureDir, CaptureFps));
}

void AShowcaseDirector::OnCaptureFrame(int32 Width, int32 Height, const TArray<FColor>& Bitmap)
{
	// a frame of the running capture, or an ordinary `shot` taken while the capture delegate is bound
	const FString File = !PendingCaptureFile.IsEmpty() ? PendingCaptureFile : FScreenshotRequest::GetFilename();
	PendingCaptureFile.Reset();
	if (File.IsEmpty() || Width <= 0 || Height <= 0 || Bitmap.Num() != Width * Height)
	{
		return;
	}
	IImageWriteQueue* Queue = GetHighResScreenshotConfig().ImageWriteQueue;
	if (Queue)
	{
		TUniquePtr<FImageWriteTask> Task = MakeUnique<FImageWriteTask>();
		Task->PixelData = MakeUnique<TImagePixelData<FColor>>(FIntPoint(Width, Height), TArray64<FColor>(Bitmap));
		Task->Filename = File;
		Task->Format = EImageFormat::PNG;
		Task->CompressionQuality = (int32)EImageCompressionQuality::Default;
		Task->bOverwriteFile = true;
		Queue->Enqueue(MoveTemp(Task));
	}
	else
	{
		FImageUtils::SaveImageByExtension(*File, FImageView(Bitmap.GetData(), Width, Height));
	}
}

void AShowcaseDirector::StopCapture()
{
	if (bCapturing || bCapturePending)
	{
		bCapturing = false;
		bCapturePending = false;
		PendingFixedStep = 0;
		TraceLine(FString::Printf(TEXT("CAPTURE stop after %d frames"), CaptureFrame));
	}
	if (ScreenshotHandle.IsValid())
	{
		UGameViewportClient::OnScreenshotCaptured().Remove(ScreenshotHandle);
		ScreenshotHandle.Reset();
	}
}

void AShowcaseDirector::UpdateCapture()
{
	if (!bCapturing)
	{
		return;
	}
	// keep the asynchronous PNG writers from falling behind
	FHighResScreenshotConfig& Cfg = GetHighResScreenshotConfig();
	if (Cfg.ImageWriteQueue && Cfg.ImageWriteQueue->GetNumPendingTasks() > 24)
	{
		Cfg.ImageWriteQueue->CreateFence().Wait();
	}
	if (CaptureFrame == 0)
	{
		TraceLine(FString::Printf(TEXT("CAPTURE first frame (frame_00000 shows t=%.3f)"), ShowTime));
	}
	const FString File = CaptureDir / FString::Printf(TEXT("frame_%05d.png"), CaptureFrame++);
	PendingCaptureFile = File;
	FScreenshotRequest::RequestScreenshot(File, false, false);
}

// ================================================================================================ benchmark
FString AShowcaseDirector::GetBenchStatus() const
{
	if (BenchState == 1)
	{
		return FString::Printf(TEXT("benchmark %s: warm-up %.1f / %.1f s"), *BenchLabel, BenchElapsed, BenchWarmup);
	}
	if (BenchState == 2)
	{
		return FString::Printf(TEXT("benchmark %s: sampling %.1f / %.1f s (%d frames)"), *BenchLabel, BenchElapsed, BenchDuration, BenchFrameMs.Num());
	}
	return FString();
}

void AShowcaseDirector::UpdateBenchmark(float Dt)
{
	if (BenchState == 0)
	{
		return;
	}
	const double Now = FPlatformTime::Seconds();
	const float RealMs = (float)((Now - BenchLastTime) * 1000.0);
	BenchLastTime = Now;
	BenchElapsed += RealMs / 1000.f;
	if (BenchState == 1)
	{
		if (BenchElapsed >= BenchWarmup)
		{
			BenchState = 2;
			BenchElapsed = 0.f;
			BenchFrameMs.Reset();
			BenchGameMs.Reset();
			BenchRenderMs.Reset();
			BenchGpuMs.Reset();
		}
		return;
	}
	BenchFrameMs.Add(RealMs);
	BenchGameMs.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));
	BenchRenderMs.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));
	BenchGpuMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)));
	if (BenchElapsed >= BenchDuration)
	{
		FinishBenchmark();
	}
}

void AShowcaseDirector::FinishBenchmark()
{
	BenchState = 0;
	auto Stats = [](TArray<float> V, float& Avg, float& Med, float& P95, float& P99, float& Max, float& Min)
	{
		Avg = Med = P95 = P99 = Max = Min = 0.f;
		if (V.Num() == 0)
		{
			return;
		}
		double Sum = 0.0;
		for (float X : V)
		{
			Sum += X;
		}
		Avg = (float)(Sum / V.Num());
		V.Sort();
		Med = V[V.Num() / 2];
		P95 = V[FMath::Min(V.Num() - 1, (int32)(V.Num() * 0.95f))];
		P99 = V[FMath::Min(V.Num() - 1, (int32)(V.Num() * 0.99f))];
		Min = V[0];
		Max = V.Last();
	};
	float Avg, Med, P95, P99, Max, Min;
	Stats(BenchFrameMs, Avg, Med, P95, P99, Max, Min);
	float GAvg, GMed, G95, G99, GMax, GMin, RAvg, RMed, R95, R99, RMax, RMin, UAvg, UMed, U95, U99, UMax, UMin;
	Stats(BenchGameMs, GAvg, GMed, G95, G99, GMax, GMin);
	Stats(BenchRenderMs, RAvg, RMed, R95, R99, RMax, RMin);
	Stats(BenchGpuMs, UAvg, UMed, U95, U99, UMax, UMin);
	FString Dir = FPaths::ProjectSavedDir() / TEXT("Benchmarks");
	FParse::Value(FCommandLine::Get(), TEXT("MorphBenchDir="), Dir);
	IFileManager::Get().MakeDirectory(*Dir, true);
	FString Csv = TEXT("frame,frame_ms,game_thread_ms,render_thread_ms,gpu_ms\n");
	for (int32 i = 0; i < BenchFrameMs.Num(); ++i)
	{
		Csv += FString::Printf(TEXT("%d,%.4f,%.4f,%.4f,%.4f\n"), i, BenchFrameMs[i], BenchGameMs[i], BenchRenderMs[i], BenchGpuMs[i]);
	}
	FFileHelper::SaveStringToFile(Csv, *(Dir / (BenchLabel + TEXT("_frames.csv"))));

	FIntPoint Size(0, 0);
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		Size = GEngine->GameViewport->Viewport->GetSizeXY();
	}
	auto CVarStr = [](const TCHAR* Name) -> FString
	{
		IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(Name);
		return V ? V->GetString() : FString(TEXT("n/a"));
	};
	FString Lods;
	if (AOperativeCharacter* Ch = GetPrimary())
	{
		if (USkeletalMesh* SK = Ch->GetMesh()->GetSkeletalMeshAsset())
		{
			if (const FSkeletalMeshRenderData* RD = SK->GetResourceForRendering())
			{
				for (int32 i = 0; i < RD->LODRenderData.Num(); ++i)
				{
					Lods += FString::Printf(TEXT("%s%d"), i ? TEXT(", ") : TEXT(""), RD->LODRenderData[i].GetTotalFaces());
				}
			}
		}
	}
	const bool bOffscreen = FParse::Param(FCommandLine::Get(), TEXT("RenderOffScreen"));
	FString Json = TEXT("{\n");
	Json += FString::Printf(TEXT(" \"label\": \"%s\",\n \"instances\": %d,\n \"sample_seconds\": %.3f,\n \"warmup_seconds\": %.3f,\n \"frames\": %d,\n"),
		*JsonEscape(BenchLabel), Instances.Num(), BenchDuration, BenchWarmup, BenchFrameMs.Num());
	Json += FString::Printf(TEXT(" \"frame_ms\": {\"avg\": %.4f, \"median\": %.4f, \"p95\": %.4f, \"p99\": %.4f, \"max\": %.4f, \"min\": %.4f},\n"), Avg, Med, P95, P99, Max, Min);
	Json += FString::Printf(TEXT(" \"fps\": {\"avg\": %.2f, \"median\": %.2f, \"p95_low\": %.2f, \"p99_low\": %.2f},\n"),
		Avg > 0 ? 1000.f / Avg : 0.f, Med > 0 ? 1000.f / Med : 0.f, P95 > 0 ? 1000.f / P95 : 0.f, P99 > 0 ? 1000.f / P99 : 0.f);
	Json += FString::Printf(TEXT(" \"game_thread_ms\": {\"avg\": %.4f, \"p95\": %.4f},\n \"render_thread_ms\": {\"avg\": %.4f, \"p95\": %.4f},\n \"gpu_ms\": {\"avg\": %.4f, \"p95\": %.4f},\n"),
		GAvg, G95, RAvg, R95, UAvg, U95);
	Json += FString::Printf(TEXT(" \"resolution\": [%d, %d],\n \"render_offscreen\": %s,\n \"fixed_time_step\": %s,\n"), Size.X, Size.Y,
		bOffscreen ? TEXT("true") : TEXT("false"), FApp::UseFixedTimeStep() ? TEXT("true") : TEXT("false"));
	Json += FString::Printf(TEXT(" \"settings\": {\"r.ScreenPercentage\": \"%s\", \"r.AntiAliasingMethod\": \"%s\", \"r.DynamicGlobalIlluminationMethod\": \"%s\", \"r.ReflectionMethod\": \"%s\", \"r.Shadow.Virtual.Enable\": \"%s\", \"r.VSync\": \"%s\", \"t.MaxFPS\": \"%s\", \"frame_generation\": \"none\", \"upscaling\": \"none (100%% screen percentage)\"},\n"),
		*CVarStr(TEXT("r.ScreenPercentage")), *CVarStr(TEXT("r.AntiAliasingMethod")), *CVarStr(TEXT("r.DynamicGlobalIlluminationMethod")),
		*CVarStr(TEXT("r.ReflectionMethod")), *CVarStr(TEXT("r.Shadow.Virtual.Enable")), *CVarStr(TEXT("r.VSync")), *CVarStr(TEXT("t.MaxFPS")));
	Json += FString::Printf(TEXT(" \"character\": {\"lod_triangles\": [%s], \"lod_mode\": %d, \"display_mode\": %d},\n"), *Lods,
		GetPrimary() ? GetPrimary()->GetLodMode() : 0, GetPrimary() ? (int32)GetPrimary()->GetDisplayMode() : 0);
	Json += FString::Printf(TEXT(" \"system\": {\"cpu\": \"%s\", \"physical_cores\": %d, \"logical_cores\": %d, \"ram_gb\": %u, \"gpu\": \"%s\", \"gpu_driver\": \"%s\", \"rhi\": \"%s\", \"os\": \"%s\"},\n"),
		*JsonEscape(FPlatformMisc::GetCPUBrand()), FPlatformMisc::NumberOfCores(), FPlatformMisc::NumberOfCoresIncludingHyperthreads(),
		FPlatformMemory::GetConstants().TotalPhysicalGB, *JsonEscape(GRHIAdapterName), *JsonEscape(GRHIAdapterUserDriverVersion),
		GDynamicRHI ? GDynamicRHI->GetName() : TEXT("none"), *JsonEscape(FPlatformMisc::GetOSVersion()));
	Json += FString::Printf(TEXT(" \"engine\": \"%s\",\n \"build_configuration\": \"%s\"\n}\n"), *JsonEscape(FApp::GetBuildVersion()),
		LexToString(FApp::GetBuildConfiguration()));
	FFileHelper::SaveStringToFile(Json, *(Dir / (BenchLabel + TEXT(".json"))));
	TraceLine(FString::Printf(TEXT("BENCH %s instances=%d frames=%d avg=%.3f ms (%.1f fps) median=%.3f p95=%.3f p99=%.3f max=%.3f gt=%.3f rt=%.3f gpu=%.3f -> %s"),
		*BenchLabel, Instances.Num(), BenchFrameMs.Num(), Avg, Avg > 0 ? 1000.f / Avg : 0.f, Med, P95, P99, Max, GAvg, RAvg, UAvg, *Dir));
}

// ================================================================================================ input injection
bool AShowcaseDirector::InjectKey(const FString& KeyName, const FString& Action)
{
	if (!FSlateApplication::IsInitialized())
	{
		return false;
	}
	const FKey Key(*KeyName);
	if (!Key.IsValid())
	{
		TraceLine(FString::Printf(TEXT("INJECT unknown key %s"), *KeyName));
		return false;
	}
	FSlateApplication& Slate = FSlateApplication::Get();
	const uint32* KeyCode = nullptr;
	const uint32* CharCode = nullptr;
	FInputKeyManager::Get().GetCodesFromKey(Key, KeyCode, CharCode);
	const FKeyEvent Event(Key, FModifierKeysState(), 0, false, CharCode ? *CharCode : 0, KeyCode ? *KeyCode : 0);
	if (Action == TEXT("down") || Action == TEXT("tap"))
	{
		Slate.ProcessKeyDownEvent(Event);
	}
	if (Action == TEXT("up") || Action == TEXT("tap"))
	{
		Slate.ProcessKeyUpEvent(Event);
	}
	return true;
}

bool AShowcaseDirector::InjectMouse(float X, float Y, const FString& Action)
{
	if (!FSlateApplication::IsInitialized() || !GEngine || !GEngine->GameViewport)
	{
		return false;
	}
	TSharedPtr<SViewport> ViewportWidget = GEngine->GameViewport->GetGameViewportWidget();
	TSharedPtr<SWindow> Window = GEngine->GameViewport->GetWindow();
	if (!ViewportWidget.IsValid() || !Window.IsValid())
	{
		return false;
	}
	const FGeometry& Geo = ViewportWidget->GetCachedGeometry();
	const FVector2D Abs = Geo.LocalToAbsolute(FVector2D(X, Y) * Geo.GetLocalSize());
	FSlateApplication& Slate = FSlateApplication::Get();
	static FVector2D Last = Abs;
	TSet<FKey> Pressed;
	const FKey Button = Action.Contains(TEXT("right")) ? EKeys::RightMouseButton : EKeys::LeftMouseButton;
	Slate.ProcessMouseMoveEvent(FPointerEvent(0, Abs, Last, Pressed, FKey(), 0.f, FModifierKeysState()));
	if (Action.StartsWith(TEXT("wheel")))
	{
		const float Delta = Action.Contains(TEXT("down")) ? -1.f : 1.f;
		Slate.ProcessMouseWheelOrGestureEvent(FPointerEvent(0, Abs, Last, Pressed, EKeys::Invalid, Delta, FModifierKeysState()), nullptr);
	}
	if (Action.StartsWith(TEXT("down")) || Action.StartsWith(TEXT("click")))
	{
		Pressed.Add(Button);
		Slate.ProcessMouseButtonDownEvent(Window->GetNativeWindow(), FPointerEvent(0, Abs, Last, Pressed, Button, 0.f, FModifierKeysState()));
	}
	if (Action.StartsWith(TEXT("up")) || Action.StartsWith(TEXT("click")))
	{
		Pressed.Reset();
		Slate.ProcessMouseButtonUpEvent(FPointerEvent(0, Abs, Last, Pressed, Button, 0.f, FModifierKeysState()));
	}
	Last = Abs;
	return true;
}

// ================================================================================================ commands
static bool OnOff(const TArray<FString>& A, int32 Index, bool Current)
{
	if (!A.IsValidIndex(Index))
	{
		return !Current;
	}
	const FString& V = A[Index];
	if (V == TEXT("toggle"))
	{
		return !Current;
	}
	return V == TEXT("on") || V == TEXT("1") || V == TEXT("true");
}

static float DirArg(const FString& S)
{
	if (S == TEXT("f") || S == TEXT("front"))
	{
		return 0.f;
	}
	if (S == TEXT("b") || S == TEXT("back"))
	{
		return 180.f;
	}
	if (S == TEXT("l") || S == TEXT("left"))
	{
		return 90.f;
	}
	if (S == TEXT("r") || S == TEXT("right"))
	{
		return -90.f;
	}
	return FCString::Atof(*S);
}

bool AShowcaseDirector::ExecCharacter(AOperativeCharacter* Ch, const TArray<FString>& A)
{
	if (!Ch || A.Num() == 0)
	{
		return false;
	}
	UOperativeStateComponent* S = Ch->StateComp;
	const FString& C = A[0];
	const FString Arg1 = A.Num() > 1 ? A[1] : FString();
	if (C == TEXT("jump")) { return S->DoJump(); }
	if (C == TEXT("dash")) { return S->DoDash(DirArg(Arg1.IsEmpty() ? TEXT("f") : Arg1)); }
	if (C == TEXT("blink"))
	{
		FVector Dest = Ch->GetActorLocation() + Ch->GetActorForwardVector() * 450.0;
		if (A.Num() >= 3)
		{
			Dest = FVector(FCString::Atof(*A[1]), FCString::Atof(*A[2]), Ch->GetActorLocation().Z);
		}
		return S->DoBlink(Dest);
	}
	if (C == TEXT("drop"))
	{
		Ch->SetActorLocation(Ch->GetActorLocation() + FVector(0, 0, 360.0), false, nullptr, ETeleportType::TeleportPhysics);
		TraceLine(TEXT("DROP character lifted 360 cm for a long fall"));
		return true;
	}
	if (C == TEXT("melee")) { return S->DoMelee(); }
	if (C == TEXT("fire")) { return S->DoRanged(false); }
	if (C == TEXT("burst")) { return S->DoRanged(true); }
	if (C == TEXT("reload")) { return S->DoReload(); }
	if (C == TEXT("cast")) { return S->DoCast(FName(*(Arg1.IsEmpty() ? FString(TEXT("directional")) : Arg1))); }
	if (C == TEXT("channel"))
	{
		if (Arg1 == TEXT("release") || Arg1 == TEXT("end")) { return S->ChannelRelease(); }
		if (Arg1 == TEXT("interrupt")) { return S->ChannelInterrupt(TEXT("interrupt command")); }
		return S->ChannelPress();
	}
	if (C == TEXT("charge"))
	{
		if (Arg1 == TEXT("release")) { return S->ChargeRelease(); }
		if (Arg1 == TEXT("cancel")) { return S->ChargeCancel(TEXT("cancel command")); }
		return S->ChargePress();
	}
	if (C == TEXT("deploy")) { return S->DoDeploy(); }
	if (C == TEXT("uplink")) { return Arg1 == TEXT("cancel") ? S->UplinkCancel(TEXT("cancel command")) : S->UplinkStart(); }
	if (C == TEXT("turn")) { return S->DoTurn(Arg1 == TEXT("r") || Arg1 == TEXT("right") ? -90.f : 90.f); }
	if (C == TEXT("hit")) { S->ApplyHit(DirArg(Arg1.IsEmpty() ? TEXT("f") : Arg1), A.Num() > 2 && A[2] == TEXT("heavy")); return true; }
	if (C == TEXT("stun")) { return S->ApplyStun(Arg1.IsEmpty() ? 2.f : FCString::Atof(*Arg1)); }
	if (C == TEXT("sleep")) { return S->ApplySleep(Arg1.IsEmpty() ? 4.f : FCString::Atof(*Arg1)); }
	if (C == TEXT("knockback")) { return S->ApplyKnockback(DirArg(Arg1.IsEmpty() ? TEXT("f") : Arg1)); }
	if (C == TEXT("knockup")) { return S->ApplyKnockup(); }
	if (C == TEXT("knockdown")) { return S->ApplyKnockdown(!(Arg1 == TEXT("back") || Arg1 == TEXT("b"))); }
	if (C == TEXT("kill")) { return S->Kill(!(Arg1 == TEXT("back") || Arg1 == TEXT("b"))); }
	if (C == TEXT("respawn")) { return S->Respawn(Ch->SpawnLocation, Ch->SpawnYaw); }
	if (C == TEXT("reset")) { S->ResetAll(); return true; }
	if (C == TEXT("flag") && A.Num() >= 2)
	{
		const FName Flag(*A[1]);
		FVector Source = Ch->GetActorLocation() + Ch->GetActorForwardVector() * 350.0;
		if (A.Num() >= 5)
		{
			Source = FVector(FCString::Atof(*A[3]), FCString::Atof(*A[4]), Ch->GetActorLocation().Z);
		}
		S->SetFlag(Flag, OnOff(A, 2, S->HasFlag(Flag)), Source);
		return true;
	}
	if (C == TEXT("wounded")) { S->bWounded = OnOff(A, 1, S->bWounded); TraceLine(FString::Printf(TEXT("WOUNDED %d"), S->bWounded ? 1 : 0)); return true; }
	if (C == TEXT("emote")) { return S->PlayEmote(FName(*(Arg1.IsEmpty() ? FString(TEXT("greet")) : Arg1))); }
	if (C == TEXT("speech"))
	{
		// the speech sample is acted with the hands at chest height: show head, shoulders and chest
		if (Ch == GetPrimary())
		{
			SetCamera(EShowcaseCamera::Bust);
		}
		return S->PlayEmote(TEXT("dialogue"));
	}
	if (C == TEXT("view")) { return (Arg1 == TEXT("refpose") || Arg1 == TEXT("reference")) ? S->ViewReferencePose() : S->ViewClip(FName(*Arg1)); }
	if (C == TEXT("refpose")) { return S->ViewReferencePose(); }
	if (C == TEXT("viewer"))
	{
		if (Arg1 == TEXT("pause")) { S->bViewerPaused = true; }
		else if (Arg1 == TEXT("play")) { S->bViewerPaused = false; }
		else if (Arg1 == TEXT("toggle")) { S->bViewerPaused = !S->bViewerPaused; }
		else if (Arg1 == TEXT("loop")) { S->bViewerLoop = OnOff(A, 2, S->bViewerLoop); }
		else if (Arg1 == TEXT("rate") && A.Num() > 2) { S->ViewerRate = FMath::Clamp(FCString::Atof(*A[2]), 0.05f, 3.f); }
		else if (Arg1 == TEXT("scrub") && A.Num() > 2) { S->ViewerScrub(FCString::Atof(*A[2])); }
		else if (Arg1 == TEXT("exit")) { S->ExitViewer(); }
		return true;
	}
	if (C == TEXT("face"))
	{
		if (Arg1 == TEXT("reset")) { S->ClearFace(); return true; }
		if (A.Num() >= 3)
		{
			// names come from face_controls.json; an unknown one is reported instead of being ignored silently
			if (!FMorphRigData::Get().Controls.Contains(FName(*A[1]))) { TraceLine(FString::Printf(TEXT("REFUSED face control '%s' is not in face_controls.json"), *A[1])); return true; }
			S->FaceDirect.Add(FName(*A[1]), FMath::Clamp(FCString::Atof(*A[2]), 0.f, 1.f));
			return true;
		}
		return false;
	}
	if (C == TEXT("viseme") && A.Num() >= 3)
	{
		if (!FMorphRigData::Get().Visemes.Contains(FName(*A[1]))) { TraceLine(FString::Printf(TEXT("REFUSED viseme '%s' is not in face_controls.json"), *A[1])); return true; }
		S->FaceVisemes.Add(FName(*A[1]), FMath::Clamp(FCString::Atof(*A[2]), 0.f, 1.f));
		return true;
	}
	if (C == TEXT("expr") && A.Num() >= 3)
	{
		if (!FMorphRigData::Get().Expressions.Contains(FName(*A[1]))) { TraceLine(FString::Printf(TEXT("REFUSED expression '%s' is not in face_controls.json"), *A[1])); return true; }
		S->FaceExpressions.Add(FName(*A[1]), FMath::Clamp(FCString::Atof(*A[2]), 0.f, 1.f));
		return true;
	}
	if (C == TEXT("bone") && A.Num() > 1)
	{
		// bone <name>: trace the bone's current local transform relative to its reference pose (rig debugging)
		USkeletalMeshComponent* SkelComp = Ch->GetMesh();
		const FName BoneName(*A[1]);
		const int32 BoneIndex = SkelComp ? SkelComp->GetBoneIndex(BoneName) : INDEX_NONE;
		if (BoneIndex == INDEX_NONE || !SkelComp->GetSkeletalMeshAsset())
		{
			TraceLine(FString::Printf(TEXT("BONE %s: not in the skeleton"), *A[1]));
			return true;
		}
		const FTransform Local = SkelComp->GetSocketTransform(BoneName, RTS_ParentBoneSpace);
		const FTransform Ref = SkelComp->GetSkeletalMeshAsset()->GetRefSkeleton().GetRefBonePose()[BoneIndex];
		const FQuat Delta = (Ref.GetRotation().Inverse() * Local.GetRotation()).GetNormalized();
		FVector Axis;
		double Angle = 0.0;
		Delta.ToAxisAndAngle(Axis, Angle);
		if (Angle > PI)
		{
			Angle = 2.0 * PI - Angle;
			Axis = -Axis;
		}
		const FVector Offset = Local.GetTranslation() - Ref.GetTranslation();
		TraceLine(FString::Printf(TEXT("BONE %s: %.2f deg about (%.2f %.2f %.2f) relative to the reference pose, translation offset (%.2f %.2f %.2f) cm"),
			*A[1], FMath::RadiansToDegrees(Angle), Axis.X, Axis.Y, Axis.Z, Offset.X, Offset.Y, Offset.Z));
		return true;
	}
	if (C == TEXT("gaze"))
	{
		if (Arg1 == TEXT("off") || A.Num() < 3) { S->bManualGaze = false; return true; }
		S->bManualGaze = true;
		S->GazeYawDeg = FCString::Atof(*A[1]);
		S->GazePitchDeg = FCString::Atof(*A[2]);
		return true;
	}
	if (C == TEXT("lookcam")) { S->bLookAtCamera = OnOff(A, 1, S->bLookAtCamera); return true; }
	if (C == TEXT("autoblink")) { S->bAutoBlink = OnOff(A, 1, S->bAutoBlink); return true; }
	if (C == TEXT("lookat")) { S->bLookAt = OnOff(A, 1, S->bLookAt); return true; }
	if (C == TEXT("footik")) { S->bFootIK = OnOff(A, 1, S->bFootIK); return true; }
	if (C == TEXT("secondary")) { S->bSimulateSecondary = OnOff(A, 1, S->bSimulateSecondary); return true; }
	if (C == TEXT("helpers")) { S->bProceduralBones = OnOff(A, 1, S->bProceduralBones); return true; }
	if (C == TEXT("strafe")) { S->bStrafe = OnOff(A, 1, S->bStrafe); TraceLine(S->bStrafe ? TEXT("MODE strafe / aim") : TEXT("MODE travel")); return true; }
	if (C == TEXT("rate") && A.Num() >= 2) { S->ActionRate = FMath::Clamp(FCString::Atof(*A[1]), 0.5f, 1.5f); TraceLine(FString::Printf(TEXT("ACTION RATE %.2fx"), S->ActionRate)); return true; }
	if (C == TEXT("team")) { Ch->SetTeam(Arg1 == TEXT("B") || Arg1 == TEXT("b") || Arg1 == TEXT("1") ? 1 : (Arg1 == TEXT("toggle") ? 1 - Ch->GetTeam() : 0)); TraceLine(FString::Printf(TEXT("TEAM %s"), Ch->GetTeam() ? TEXT("B") : TEXT("A"))); return true; }
	if (C == TEXT("outline")) { Ch->SetOutline(OnOff(A, 1, Ch->HasOutline())); return true; }
	if (C == TEXT("ring")) { Ch->SetRing(OnOff(A, 1, Ch->HasRing())); return true; }
	if (C == TEXT("lod"))
	{
		const int32 Mode = Arg1 == TEXT("auto") ? 0 : (Arg1 == TEXT("cycle") ? (Ch->GetLodMode() + 1) % 4 : FCString::Atoi(*Arg1) + 1);
		Ch->SetLodMode(Mode);
		TraceLine(FString::Printf(TEXT("LOD %s"), Mode == 0 ? TEXT("auto") : *FString::FromInt(Mode - 1)));
		return true;
	}
	if (C == TEXT("display"))
	{
		EOpDisplayMode Mode = EOpDisplayMode::Textured;
		if (Arg1 == TEXT("wireframe") || Arg1 == TEXT("mesh")) { Mode = EOpDisplayMode::Wireframe; }
		else if (Arg1 == TEXT("normals")) { Mode = EOpDisplayMode::Normals; }
		else if (Arg1 == TEXT("clay")) { Mode = EOpDisplayMode::Clay; }
		else if (Arg1 == TEXT("cycle")) { Mode = (EOpDisplayMode)(((int32)Ch->GetDisplayMode() + 1) % 4); }
		Ch->SetDisplayMode(Mode);
		return true;
	}
	if (C == TEXT("goto"))
	{
		FVector P = Ch->SpawnLocation;
		float Yaw = Ch->SpawnYaw;
		if (Room)
		{
			if (Arg1 == TEXT("station")) { P = Room->StationPoint; Yaw = -90.f; }
			else if (Arg1 == TEXT("viewer")) { P = Room->ViewerPoint; Yaw = -45.f; }
			else if (Arg1 == TEXT("ramp")) { P = Room->RampBottom; Yaw = 0.f; }
			else if (Arg1 == TEXT("steps")) { P = Room->StepsBottom; Yaw = 0.f; }
			else if (Arg1 == TEXT("top")) { P = Room->RampTop; Yaw = 180.f; }
		}
		if (A.Num() >= 3 && Arg1.IsNumeric())
		{
			P = FVector(FCString::Atof(*A[1]), FCString::Atof(*A[2]), 92.0);
		}
		S->ExitViewer();
		Ch->SetActorLocation(P, false, nullptr, ETeleportType::TeleportPhysics);
		Ch->SetActorRotation(FRotator(0, Yaw, 0));
		Ch->GetCharacterMovement()->StopMovementImmediately();
		bCamSnap = true;
		return true;
	}
	return false;
}

bool AShowcaseDirector::Exec(const FString& Line)
{
	TArray<FString> A;
	Line.TrimStartAndEnd().ParseIntoArrayWS(A);
	if (A.Num() == 0)
	{
		return false;
	}
	const FString C = A[0].ToLower();
	A[0] = C;
	const FString Arg1 = A.Num() > 1 ? A[1] : FString();
	if (C != TEXT("key") && C != TEXT("mouse") && C != TEXT("log"))
	{
		TraceLine(FString::Printf(TEXT("CMD %s"), *Line.TrimStartAndEnd()));
	}
	if (C == TEXT("log"))
	{
		const FString Text = Line.TrimStartAndEnd().Mid(4);
		TraceLine(Text);
		if (Text.StartsWith(TEXT("SEQUENCE ")))
		{
			Caption = Text.Mid(9);
			CaptionTime = 5.f;
		}
		return true;
	}
	if (C == TEXT("caption"))
	{
		Caption = Line.TrimStartAndEnd().Mid(8);
		CaptionTime = Caption.IsEmpty() ? 0.f : 1.e6f;
		return true;
	}
	if (C == TEXT("help"))
	{
		bShowHelp = OnOff(A, 1, bShowHelp);
		return true;
	}
	if (C == TEXT("hud")) { bShowHud = OnOff(A, 1, bShowHud); return true; }
	if (C == TEXT("skeleton")) { bShowSkeleton = OnOff(A, 1, bShowSkeleton); return true; }
	if (C == TEXT("panel"))
	{
		if (Arg1 == TEXT("tab") && A.Num() > 2)
		{
			if (AShowcasePlayerController* PC = Cast<AShowcasePlayerController>(UGameplayStatics::GetPlayerController(this, 0)))
			{
				PC->SetPanelTab(A[2]);
			}
			bShowPanel = true;
			return true;
		}
		bShowPanel = OnOff(A, 1, bShowPanel);
		return true;
	}
	if (C == TEXT("cam"))
	{
		if (Arg1 == TEXT("top")) { SetCamera(EShowcaseCamera::TopDown); }
		else if (Arg1 == TEXT("third")) { SetCamera(EShowcaseCamera::ThirdPerson); }
		else if (Arg1 == TEXT("front")) { SetCamera(EShowcaseCamera::Front); }
		else if (Arg1 == TEXT("side")) { SetCamera(EShowcaseCamera::Side); }
		else if (Arg1 == TEXT("face")) { SetCamera(EShowcaseCamera::Face); }
		else if (Arg1 == TEXT("bust")) { SetCamera(EShowcaseCamera::Bust); }
		else if (Arg1 == TEXT("orbit")) { SetCamera(EShowcaseCamera::Orbit); }
		else if (Arg1 == TEXT("turntable")) { SetCamera(EShowcaseCamera::Turntable); if (A.Num() > 2) { TurntableSpeed = FCString::Atof(*A[2]); } }
		else if (Arg1 == TEXT("cycle"))
		{
			static const EShowcaseCamera Order[] = { EShowcaseCamera::TopDown, EShowcaseCamera::ThirdPerson, EShowcaseCamera::Front, EShowcaseCamera::Side,
				EShowcaseCamera::Bust, EShowcaseCamera::Face, EShowcaseCamera::Orbit };
			int32 Index = 0;
			for (int32 i = 0; i < UE_ARRAY_COUNT(Order); ++i)
			{
				if (Order[i] == CameraMode) { Index = i; }
			}
			SetCamera(Order[(Index + 1) % UE_ARRAY_COUNT(Order)]);
		}
		else { return false; }
		return true;
	}
	if (C == TEXT("light") && A.Num() > 4)
	{
		if (Room)
		{
			Room->SetLighting(FCString::Atof(*A[1]), FCString::Atof(*A[2]), FCString::Atof(*A[3]), FCString::Atof(*A[4]));
		}
		return true;
	}
	if (C == TEXT("camdist") && A.Num() > 1)
	{
		// distance of the current view: face and bust close-ups have their own, every other view sets the top-down distance
		const float V = FCString::Atof(*A[1]);
		if (CameraMode == EShowcaseCamera::Face) { FaceDistance = FMath::Clamp(V, 40.f, 400.f); }
		else if (CameraMode == EShowcaseCamera::Bust) { BustDistance = FMath::Clamp(V, 80.f, 600.f); }
		else { TopDownDistance = FMath::Clamp(V, 400.f, 4000.f); }
		return true;
	}
	if (C == TEXT("shadow") && A.Num() > 2)
	{
		// shadow <amount 0..1> <source angle deg> [<close-up amount> <close-up angle>]: key light shadow darkness and softness
		KeyShadowAmount = FCString::Atof(*A[1]);
		KeySourceAngle = FCString::Atof(*A[2]);
		if (A.Num() > 4)
		{
			CloseShadowAmount = FCString::Atof(*A[3]);
			CloseSourceAngle = FCString::Atof(*A[4]);
		}
		if (A.Num() > 7)
		{
			// ... [<close-up key intensity scale> <yaw offset to the view> <elevation>]
			CloseKeyScale = FCString::Atof(*A[5]);
			CloseKeyYawOffset = FCString::Atof(*A[6]);
			CloseKeyPitch = FCString::Atof(*A[7]);
		}
		AppliedKeyLook = -1;
		return true;
	}
	if (C == TEXT("orbit") && A.Num() > 3) { OrbitYaw = FCString::Atof(*A[1]); OrbitPitch = FCString::Atof(*A[2]); OrbitDistance = FCString::Atof(*A[3]); return true; }
	if (C == TEXT("instances")) { SetInstanceCount(Arg1 == TEXT("toggle") ? (Instances.Num() > 1 ? 1 : 10) : FCString::Atoi(*Arg1)); return true; }
	if (C == TEXT("select")) { Selected = FMath::Clamp(FCString::Atoi(*Arg1), 0, Instances.Num() - 1); return true; }
	if (C == TEXT("sequence")) { StartSequence(); return true; }
	if (C == TEXT("script")) { return RunScriptFile(Arg1); }
	if (C == TEXT("stopscript")) { ScriptLines.Reset(); bScriptedInput = false; ScriptMove = FVector::ZeroVector; return true; }
	if (C == TEXT("quit")) { StopCapture(); FPlatformMisc::RequestExit(false); return true; }
	if (C == TEXT("exec") && A.Num() > 1)
	{
		if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
		{
			PC->ConsoleCommand(Line.TrimStartAndEnd().Mid(5));
		}
		return true;
	}
	if (C == TEXT("shot") && A.Num() > 1)
	{
		const bool bUI = A.Num() > 2 && A[2] == TEXT("ui");
		FScreenshotRequest::RequestScreenshot(A[1], bUI, false);
		return true;
	}
	if (C == TEXT("autoshot"))
	{
		// autoshot <seconds> <dir> | autoshot off : one screenshot every <seconds> of showcase time (quick visual review of a long script)
		if (A.Num() > 2 && FCString::Atof(*A[1]) > 0.f)
		{
			AutoShotInterval = FCString::Atof(*A[1]);
			AutoShotDir = A[2];
			AutoShotIndex = 0;
			NextAutoShot = ShowTime;
			IFileManager::Get().MakeDirectory(*AutoShotDir, true);
		}
		else
		{
			AutoShotInterval = 0.f;
		}
		return true;
	}
	if (C == TEXT("capture"))
	{
		if (Arg1 == TEXT("stop")) { StopCapture(); return true; }
		if (Arg1 == TEXT("start"))
		{
			const FString Dir = (A.Num() > 2 && A[2] != TEXT("default")) ? A[2] : CaptureDirDefault;
			StartCapture(Dir, A.Num() > 3 ? FCString::Atof(*A[3]) : 30.f);
			return true;
		}
		return false;
	}
	if (C == TEXT("bench") && A.Num() > 3)
	{
		BenchWarmup = FCString::Atof(*A[1]);
		BenchDuration = FCString::Atof(*A[2]);
		BenchLabel = A[3];
		BenchElapsed = 0.f;
		BenchState = 1;
		BenchLastTime = FPlatformTime::Seconds();
		TraceLine(FString::Printf(TEXT("BENCH %s started: warm-up %.1f s, sample %.1f s, %d instance(s)"), *BenchLabel, BenchWarmup, BenchDuration, Instances.Num()));
		return true;
	}
	if (C == TEXT("key") && A.Num() > 2) { return InjectKey(A[1], A[2].ToLower()); }
	if (C == TEXT("mouse") && A.Num() > 3) { return InjectMouse(FCString::Atof(*A[1]), FCString::Atof(*A[2]), A[3].ToLower()); }
	if (C == TEXT("type") && A.Num() > 1)
	{
		if (FSlateApplication::IsInitialized())
		{
			const FString Text = Line.TrimStartAndEnd().Mid(5);
			for (TCHAR Ch : Text)
			{
				FSlateApplication::Get().ProcessKeyCharEvent(FCharacterEvent(Ch, FModifierKeysState(), 0, false));
			}
		}
		return true;
	}
	// ---- scripted intent
	if (C == TEXT("move"))
	{
		if (Arg1 == TEXT("stop") || A.Num() < 3)
		{
			ScriptMove = FVector::ZeroVector;
			ScriptMoveTime = 0.f;
		}
		else
		{
			ScriptMove = FVector(FCString::Atof(*A[1]), FCString::Atof(*A[2]), 0).GetClampedToMaxSize(1.0);
			ScriptMoveTime = A.Num() > 3 ? FCString::Atof(*A[3]) : 0.f;
		}
		bScriptedInput = true;
		return true;
	}
	if (C == TEXT("scriptinput")) { bScriptedInput = OnOff(A, 1, bScriptedInput); return true; }
	if (C == TEXT("sprint")) { bScriptSprint = OnOff(A, 1, bScriptSprint); return true; }
	if (C == TEXT("walk")) { bScriptWalk = OnOff(A, 1, bScriptWalk); return true; }
	if (C == TEXT("speed")) { ScriptSpeed = Arg1.IsNumeric() ? FCString::Atof(*Arg1) : -1.f; return true; }
	if (C == TEXT("aim")) { bScriptAim = OnOff(A, 1, bScriptAim); return true; }
	if (C == TEXT("aimat") && A.Num() > 3) { bScriptAimPoint = true; ScriptAimPoint = FVector(FCString::Atof(*A[1]), FCString::Atof(*A[2]), FCString::Atof(*A[3])); LockedTarget = INDEX_NONE; return true; }
	if (C == TEXT("aimclear")) { bScriptAimPoint = false; LockTarget(INDEX_NONE); return true; }
	if (C == TEXT("aimtarget")) { LockTarget(Arg1 == TEXT("cycle") ? ((LockedTarget + 2) % (Room ? Room->NumTargets() + 1 : 1)) - 1 : FCString::Atoi(*Arg1)); return true; }
	if (C == TEXT("target") && A.Num() > 4)
	{
		if (Room)
		{
			Room->SetAimTargetLocation(FCString::Atoi(*A[1]), FVector(FCString::Atof(*A[2]), FCString::Atof(*A[3]), FCString::Atof(*A[4])));
		}
		return true;
	}
	// ---- character commands (optionally for every instance)
	if (C == TEXT("all"))
	{
		TArray<FString> Rest(A);
		Rest.RemoveAt(0);
		bool bAny = false;
		for (AOperativeCharacter* Ch : Instances)
		{
			bAny |= ExecCharacter(Ch, Rest);
		}
		return bAny;
	}
	AOperativeCharacter* Ch = Instances.IsValidIndex(Selected) ? Instances[Selected].Get() : GetPrimary();
	const bool bOk = ExecCharacter(Ch, A);
	if (!bOk && C != TEXT("jump") && C != TEXT("dash") && C != TEXT("melee") && C != TEXT("fire") && C != TEXT("burst") && C != TEXT("reload") && C != TEXT("cast")
		&& C != TEXT("channel") && C != TEXT("charge") && C != TEXT("deploy") && C != TEXT("uplink") && C != TEXT("turn") && C != TEXT("stun") && C != TEXT("sleep")
		&& C != TEXT("knockback") && C != TEXT("knockup") && C != TEXT("knockdown") && C != TEXT("kill") && C != TEXT("respawn") && C != TEXT("emote") && C != TEXT("speech")
		&& C != TEXT("blink") && C != TEXT("view"))
	{
		TraceLine(FString::Printf(TEXT("CMD unknown: %s"), *Line));
	}
	return bOk;
}
