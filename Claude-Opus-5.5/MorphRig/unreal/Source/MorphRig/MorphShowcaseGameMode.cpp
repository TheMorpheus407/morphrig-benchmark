#include "MorphShowcaseGameMode.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextRenderActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "MorphClipLibrary.h"
#include "MorphHUD.h"
#include "MorphOperative.h"
#include "MorphPanels.h"
#include "MorphPlayerController.h"
#include "RHI.h"
#include "RenderCore.h"
#include "UnrealClient.h"
#include "Widgets/SWeakWidget.h"

DEFINE_LOG_CATEGORY_STATIC(LogMorphShowcase, Log, All);

namespace
{
	const FVector StartLoc(0.f, 0.f, 100.f);
	const FVector ViewerLoc(-700.f, 650.f, 20.f);
	const FVector SeqStartLoc(-2600.f, 1800.f, 100.f);
}

AMorphShowcaseGameMode::AMorphShowcaseGameMode()
{
	DefaultPawnClass = AMorphOperative::StaticClass();
	PlayerControllerClass = AMorphPlayerController::StaticClass();
	HUDClass = AMorphHUD::StaticClass();
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bTickEvenWhenPaused = true;
}

AMorphOperative* AMorphShowcaseGameMode::GetPlayerOperative() const
{
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	return PC ? Cast<AMorphOperative>(PC->GetPawn()) : nullptr;
}

// ===================================================================================== room
AStaticMeshActor* AMorphShowcaseGameMode::Block(const FVector& Loc, const FVector& SizeCm, const FRotator& Rot,
                                                const TCHAR* Mesh, const TCHAR* Mat, bool bCollide)
{
	UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, Mesh);
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* A = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), Loc, Rot, P);
	A->SetMobility(EComponentMobility::Movable);
	UStaticMeshComponent* C = A->GetStaticMeshComponent();
	C->SetStaticMesh(SM);
	C->SetWorldScale3D(SizeCm / 100.f);       // engine basic shapes are 100 cm
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Mat))
	{
		C->SetMaterial(0, M);
	}
	C->SetCollisionEnabled(bCollide ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	C->SetCollisionResponseToAllChannels(ECR_Block);
	return A;
}

void AMorphShowcaseGameMode::Label(const FVector& Loc, const FString& Text, float Size, const FRotator& Rot)
{
	ATextRenderActor* T = GetWorld()->SpawnActor<ATextRenderActor>(ATextRenderActor::StaticClass(), Loc, Rot);
	UTextRenderComponent* C = T->GetTextRender();
	C->SetText(FText::FromString(Text));
	C->SetWorldSize(Size);
	C->SetHorizontalAlignment(EHTA_Center);
	C->SetTextRenderColor(FColor(220, 225, 235));
	Labels.Add(T);
}

void AMorphShowcaseGameMode::FaceLights()
{
	// inspection lighting: key light 30 deg to the side of the view direction, fill 30 deg to the other side,
	// so every camera (third person, side, front, top-down, face) sees the lit side of the character
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (!PC || !PC->PlayerCameraManager)
	{
		return;
	}
	const float ViewYaw = PC->PlayerCameraManager->GetCameraRotation().Yaw;
	if (Sun)
	{
		Sun->GetLightComponent()->SetWorldRotation(FRotator(-40.f, ViewYaw + 30.f, 0.f));
	}
	if (Fill)
	{
		Fill->GetLightComponent()->SetWorldRotation(FRotator(-15.f, ViewYaw - 30.f, 0.f));
	}
}

void AMorphShowcaseGameMode::FaceLabels()
{
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (!PC || !PC->PlayerCameraManager)
	{
		return;
	}
	const FVector Cam = PC->PlayerCameraManager->GetCameraLocation();
	for (AActor* L : Labels)
	{
		if (L)
		{
			// text renders face +X: yaw the label toward the camera (upright, no pitch)
			const FVector To = Cam - L->GetActorLocation();
			L->SetActorRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
		}
	}
}

void AMorphShowcaseGameMode::BuildRoom()
{
	const TCHAR* Cube = TEXT("/Engine/BasicShapes/Cube.Cube");
	const TCHAR* Cyl = TEXT("/Engine/BasicShapes/Cylinder.Cylinder");
	const TCHAR* Sph = TEXT("/Engine/BasicShapes/Sphere.Sphere");
	const TCHAR* Floor = TEXT("/Game/MorphRig/Materials/M_Floor.M_Floor");
	const TCHAR* Grey = TEXT("/Game/MorphRig/Materials/M_Block.M_Block");
	const TCHAR* Tgt = TEXT("/Game/MorphRig/Materials/M_Target.M_Target");
	Block(FVector(0.f, 0.f, -10.f), FVector(12000.f, 12000.f, 20.f), FRotator::ZeroRotator, Cube, Floor);
	// ramp (20 degrees) up to a platform, steps (5 x 20 cm) on the other side
	const float Ang = 20.f, Len = 320.f, Th = 20.f;
	const float Rise = Len * FMath::Sin(FMath::DegreesToRadians(Ang));
	const float Run = Len * FMath::Cos(FMath::DegreesToRadians(Ang));
	const FVector R0(700.f, -650.f, 0.f);
	Block(R0 + FVector(Run * 0.5f, 0.f, Rise * 0.5f - Th * 0.5f / FMath::Cos(FMath::DegreesToRadians(Ang))),
	      FVector(Len, 260.f, Th), FRotator(Ang, 0.f, 0.f), Cube, Grey);
	const float PlatH = 100.f;
	const FVector Plat = R0 + FVector(Run + 150.f, 0.f, 0.f);
	Block(Plat + FVector(0.f, 0.f, PlatH * 0.5f), FVector(300.f, 260.f, PlatH), FRotator::ZeroRotator, Cube, Grey);
	for (int32 i = 0; i < 5; ++i)
	{
		const float H = 20.f * (i + 1);
		Block(Plat + FVector(150.f + 40.f * (4 - i) + 20.f, 0.f, H * 0.5f), FVector(40.f, 260.f, H),
		      FRotator::ZeroRotator, Cube, Grey);
	}
	Label(R0 + FVector(Run * 0.5f, -170.f, 60.f), TEXT("RAMP 20 deg"), 30.f, FRotator(0.f, 90.f, 0.f));
	Label(Plat + FVector(260.f, -170.f, 140.f), TEXT("STEPS 5 x 20 cm"), 30.f, FRotator(0.f, 90.f, 0.f));
	// movable aim targets
	const FVector TL[3] = {FVector(650.f, 450.f, 160.f), FVector(950.f, 0.f, 260.f), FVector(420.f, -250.f, 60.f)};
	for (int32 i = 0; i < 3; ++i)
	{
		AStaticMeshActor* T = Block(TL[i], FVector(40.f), FRotator::ZeroRotator, Sph, Tgt, false);
		Targets.Add(T);
	}
	Label(FVector(650.f, 450.f, 230.f), TEXT("AIM TARGETS (Tab select, arrows / PgUp / PgDn move, M aim at target)"), 18.f);
	// prop-contact station
	Block(FVector(-600.f, -500.f, 45.f), FVector(140.f, 70.f, 90.f), FRotator::ZeroRotator, Cube, Grey);
	Block(FVector(-600.f, -400.f, 1.f), FVector(160.f, 160.f, 2.f), FRotator::ZeroRotator, Cube, Tgt, false);
	Label(FVector(-600.f, -500.f, 130.f), TEXT("PROP STATION  R reload cell / 6 deploy beacon / 7 uplink"), 18.f);
	// motion viewer pedestal
	Block(ViewerLoc + FVector(0.f, 0.f, -10.f), FVector(300.f, 300.f, 20.f), FRotator::ZeroRotator, Cyl, Grey);
	Label(ViewerLoc + FVector(0.f, -190.f, 190.f), TEXT("MOTION VIEWER (F4 browser: Shift+click plays here)"), 18.f);
	// lighting
	const float SunYaw = -150.f, SunPitch = -40.f;   // initial; FaceLights() keeps key / fill relative to the view
	Sun = GetWorld()->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(),
		FVector(0.f, 0.f, 800.f), FRotator(SunPitch, SunYaw, 0.f));
	Sun->SetMobility(EComponentMobility::Movable);
	if (UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
	{
		L->SetIntensity(6.f);
		L->SetAtmosphereSunLight(true);
		L->SetWorldRotation(FRotator(SunPitch, SunYaw, 0.f));
		L->MarkRenderStateDirty();
		UE_LOG(LogMorphShowcase, Log, TEXT("sun rotation %s dir %s"), *L->GetComponentRotation().ToString(),
		       *L->GetForwardVector().ToString());
	}
	// soft fill from the other front side (no shadows) so faces never fall into black
	Fill = GetWorld()->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(),
		FVector(0.f, 0.f, 800.f), FRotator::ZeroRotator);
	Fill->SetMobility(EComponentMobility::Movable);
	if (UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(Fill->GetLightComponent()))
	{
		L->SetWorldRotation(FRotator(-15.f, SunYaw - 60.f, 0.f));   // mirrored about the front axis
		L->SetIntensity(1.6f);
		L->SetLightColor(FLinearColor(0.85f, 0.92f, 1.f));
		L->SetCastShadows(false);
		L->SetAtmosphereSunLight(false);
		L->SetSpecularScale(0.3f);
	}
	AActor* SkyA = GetWorld()->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity);
	USkyAtmosphereComponent* Atm = NewObject<USkyAtmosphereComponent>(SkyA);
	SkyA->SetRootComponent(Atm);
	Atm->RegisterComponent();
	ASkyLight* Sky = GetWorld()->SpawnActor<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity);
	if (USkyLightComponent* SL = Sky->GetLightComponent())
	{
		SL->SetMobility(EComponentMobility::Movable);
		SL->bRealTimeCapture = true;
		SL->SetIntensity(1.8f);
		SL->bLowerHemisphereIsBlack = false;
		SL->RecaptureSky();
	}
	APostProcessVolume* PPV = GetWorld()->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(),
		FTransform::Identity);
	PPV->bUnbound = true;
	PPV->Settings.bOverride_AutoExposureMethod = true;
	PPV->Settings.AutoExposureMethod = AEM_Manual;
	PPV->Settings.bOverride_AutoExposureBias = true;
	PPV->Settings.AutoExposureBias = 10.5f;
	PPV->Settings.bOverride_BloomIntensity = true;
	PPV->Settings.BloomIntensity = 0.2f;       // keep the emissive piping crisp
	PPV->Settings.bOverride_MotionBlurAmount = true;
	PPV->Settings.MotionBlurAmount = 0.f;
	if (UMaterialInterface* Outline = LoadObject<UMaterialInterface>(nullptr,
		TEXT("/Game/MorphRig/Materials/M_Outline.M_Outline")))
	{
		PPV->Settings.WeightedBlendables.Array.Add(FWeightedBlendable(1.f, Outline));
	}
}

FVector AMorphShowcaseGameMode::GetAimTargetLocation(int32 I) const
{
	return Targets.IsValidIndex(I) && Targets[I] ? Targets[I]->GetActorLocation() : FVector::ZeroVector;
}

void AMorphShowcaseGameMode::MoveTarget(int32 I, const FVector& Delta)
{
	if (Targets.IsValidIndex(I) && Targets[I])
	{
		FVector L = Targets[I]->GetActorLocation() + Delta;
		L.Z = FMath::Clamp(L.Z, 20.f, 400.f);
		Targets[I]->SetActorLocation(L);
	}
}

// ===================================================================================== start
void AMorphShowcaseGameMode::StartPlay()
{
	Library = NewObject<UMorphClipLibrary>(this);
	Library->Load();
	BuildRoom();
	Super::StartPlay();
	TracePath = FPaths::ProjectLogDir() / TEXT("MorphRig_Trace.txt");
	if (AMorphOperative* P = GetPlayerOperative())
	{
		P->SetLibrary(Library);
		P->SetActorLocation(StartLoc);
		P->OnTrace.AddUObject(this, &AMorphShowcaseGameMode::OnTrace);
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	Viewer = GetWorld()->SpawnActor<AMorphOperative>(AMorphOperative::StaticClass(), ViewerLoc + FVector(0, 0, 92.f),
	                                                 FRotator(0.f, -90.f, 0.f), SP);
	if (Viewer)
	{
		Viewer->SetLibrary(Library);
		Viewer->SetTeam(1);
		Viewer->SpawnDefaultController();
	}
	// command line modes
	const TCHAR* Cmd = FCommandLine::Get();
	float BenchSecs = 0.f;
	int32 NumInst = 1;
	FParse::Value(Cmd, TEXT("MorphInstances="), NumInst);
	if (FParse::Value(Cmd, TEXT("MorphBench="), BenchSecs))
	{
		float Warm = 5.f;
		FParse::Value(Cmd, TEXT("MorphBenchWarmup="), Warm);
		StartBenchmark(BenchSecs, Warm, NumInst);
	}
	else if (NumInst > 1)
	{
		SetInstanceCount(NumInst);
	}
	if (AMorphOperative* P = GetPlayerOperative())
	{
		int32 Team = 0, Lod = 0;
		if (FParse::Value(Cmd, TEXT("MorphTeam="), Team)) P->SetTeam(Team);
		if (FParse::Value(Cmd, TEXT("MorphLOD="), Lod)) P->SetForcedLOD(Lod);     // 0 auto, 1..3 = LOD0..LOD2
		if (FParse::Param(Cmd, TEXT("MorphOutline"))) P->SetOutline(true);
	}
	FString Capture;
	if (FParse::Value(Cmd, TEXT("MorphCapture="), Capture))
	{
		FString Dir = FPaths::ProjectSavedDir() / TEXT("Capture");
		FParse::Value(Cmd, TEXT("MorphCaptureDir="), Dir);
		StartCapture(Capture, Dir);
	}
	else if (FParse::Param(Cmd, TEXT("MorphSequence")))
	{
		StartSequence(FParse::Param(Cmd, TEXT("MorphExit")));
	}
	UE_LOG(LogMorphShowcase, Log, TEXT("showcase ready: %d clips, %d inventory entries"), Library->All().Num(),
	       Library->NumRequired());
}

void AMorphShowcaseGameMode::EndPlay(const EEndPlayReason::Type Reason)
{
	if (GEngine && GEngine->GameViewport)
	{
		if (BrowserWidget.IsValid())
		{
			GEngine->GameViewport->RemoveViewportWidgetContent(BrowserWidget.ToSharedRef());
		}
		if (FaceWidget.IsValid())
		{
			GEngine->GameViewport->RemoveViewportWidgetContent(FaceWidget.ToSharedRef());
		}
	}
	BrowserWidget.Reset();
	FaceWidget.Reset();
	Super::EndPlay(Reason);
}

void AMorphShowcaseGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	FaceLabels();
	FaceLights();
	TickSequence(DeltaSeconds);
	TickBenchmark(DeltaSeconds);
	TickCapture(DeltaSeconds);
}

// ===================================================================================== instances
void AMorphShowcaseGameMode::SetInstanceCount(int32 Num)
{
	Num = FMath::Clamp(Num, 1, 10);
	while (Instances.Num() > Num - 1)
	{
		if (Instances.Last())
		{
			Instances.Last()->Destroy();
		}
		Instances.Pop();
	}
	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	while (Instances.Num() < Num - 1)
	{
		const int32 i = Instances.Num();
		const float A = 2.f * PI * i / 9.f;
		const FVector L(FMath::Cos(A) * 650.f - 150.f, FMath::Sin(A) * 650.f, 100.f);
		AMorphOperative* O = GetWorld()->SpawnActor<AMorphOperative>(AMorphOperative::StaticClass(), L,
			FRotator(0.f, FMath::RadiansToDegrees(A) + 180.f, 0.f), SP);
		if (!O)
		{
			break;
		}
		O->SpawnDefaultController();
		O->SetLibrary(Library);
		O->SetTeam(i % 2);
		O->SetAutoPilot(true, 1234 + i);
		Instances.Add(O);
	}
	UE_LOG(LogMorphShowcase, Log, TEXT("instances: %d"), GetInstanceCount());
}

// ===================================================================================== panels
void AMorphShowcaseGameMode::ToggleBrowser()
{
	if (!GEngine || !GEngine->GameViewport)
	{
		return;
	}
	AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController());
	if (BrowserWidget.IsValid())
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(BrowserWidget.ToSharedRef());
		BrowserWidget.Reset();
		if (PC) PC->SetUIFocus(FaceWidget.IsValid());
		return;
	}
	TSharedRef<SMorphBrowser> W = SNew(SMorphBrowser).GameMode(this);
	BrowserWidget = W;
	GEngine->GameViewport->AddViewportWidgetContent(W, 20);
	if (PC) PC->SetUIFocus(true);
	W->FocusSearch();
}

void AMorphShowcaseGameMode::ToggleFacePanel()
{
	if (!GEngine || !GEngine->GameViewport)
	{
		return;
	}
	AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController());
	AMorphOperative* O = GetPlayerOperative();
	if (FaceWidget.IsValid())
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(FaceWidget.ToSharedRef());
		FaceWidget.Reset();
		if (O) O->SetFacePanelActive(false);
		if (PC) PC->SetUIFocus(BrowserWidget.IsValid());
		return;
	}
	TSharedRef<SMorphFacePanel> W = SNew(SMorphFacePanel).Operative(O);
	FaceWidget = W;
	GEngine->GameViewport->AddViewportWidgetContent(W, 21);
	if (O) O->SetFacePanelActive(true);
	if (PC)
	{
		PC->SetUIFocus(true);
		PC->SetCamMode(EMorphCamera::Face);
	}
}

void AMorphShowcaseGameMode::PreviewClip(FName Id, bool bLoop, bool bOnViewer)
{
	AMorphOperative* O = bOnViewer ? Viewer.Get() : GetPlayerOperative();
	if (O)
	{
		O->CmdPreview(Id, bLoop);
	}
}

// ===================================================================================== trace
void AMorphShowcaseGameMode::OnTrace(AMorphOperative* Who, const FString& Text)
{
	if (!bSequence)
	{
		return;
	}
	const FVector L = Who->GetActorLocation();
	WriteTraceLine(FString::Printf(TEXT("%8.3f\t%s\t%s\t%s\t%.1f\t%.0f,%.0f,%.0f"), SeqTime, *Who->StateName(),
	                               *Who->CurrentClipName(), *Text, Who->GetSpeedCms(), L.X, L.Y, L.Z));
}

void AMorphShowcaseGameMode::WriteTraceLine(const FString& Line)
{
	TraceLines.Add(Line);
	UE_LOG(LogMorphShowcase, Log, TEXT("TRACE %s"), *Line);
}

// ===================================================================================== sequence
void AMorphShowcaseGameMode::SetFixedStep(float Dt)
{
	FApp::SetUseFixedTimeStep(Dt > 0.f);
	if (Dt > 0.f)
	{
		FApp::SetFixedDeltaTime(Dt);
	}
}

void AMorphShowcaseGameMode::BuildSequence()
{
	Steps.Reset();
	auto Add = [this](float T, const TCHAR* L, TFunction<void(AMorphOperative*)> F) {
		Steps.Add({T, FString(L), MoveTemp(F)});
	};
	auto Move = [](float X, float Y, float S) {
		return [X, Y, S](AMorphOperative* O) { O->SetMoveInput(FVector2D(X, Y), S); };
	};
	const FVector Fwd(1.f, 0.f, 0.f);
	Add(0.0f, TEXT("reset, relaxed idle"), [](AMorphOperative* O) { O->CmdResetCharacter(); O->SetStrafe(true);
		O->SetAimInput(false, O->GetActorLocation() + FVector(100000.f, 0.f, 0.f)); });   // far point = facing direction
	Add(1.5f, TEXT("start + walk forward"), Move(1.f, 0.f, 0.375f));
	Add(3.5f, TEXT("run forward"), Move(1.f, 0.f, 1.f));
	Add(5.0f, TEXT("strafe left while facing forward"), Move(0.f, -1.f, 1.f));
	Add(6.2f, TEXT("run back-right (independent facing)"), Move(-0.7f, 0.7f, 1.f));
	Add(7.4f, TEXT("walk forward"), Move(1.f, 0.f, 0.375f));
	Add(8.8f, TEXT("stop"), Move(0.f, 0.f, 0.f));
	Add(10.0f, TEXT("sprint"), [](AMorphOperative* O) { O->SetSprint(true); O->SetMoveInput(FVector2D(1.f, 0.f), 1.f); });
	Add(11.6f, TEXT("sprint -> stop"), [](AMorphOperative* O) { O->SetSprint(false); O->SetMoveInput(FVector2D::ZeroVector, 0.f); });
	Add(13.0f, TEXT("turn left 90 (aim target to the left)"), [](AMorphOperative* O) {
		O->SetAimInput(false, O->GetActorLocation() + FVector(0.f, -100000.f, 0.f)); });
	Add(14.5f, TEXT("jump"), [](AMorphOperative* O) { O->CmdJump(); });
	Add(16.2f, TEXT("dash forward (root motion 2 m)"), [](AMorphOperative* O) { O->CmdDash(); });
	Add(17.2f, TEXT("melee combo 1-2-3"), [](AMorphOperative* O) { O->CmdMelee(); });
	Add(17.6f, TEXT("combo input"), [](AMorphOperative* O) { O->CmdMelee(); });
	Add(17.9f, TEXT("combo input"), [](AMorphOperative* O) { O->CmdMelee(); });
	Add(20.2f, TEXT("walk + fire (upper-body layer)"), [](AMorphOperative* O) {
		O->SetMoveInput(FVector2D(0.f, 1.f), 0.375f); O->CmdFire(false); });
	Add(21.0f, TEXT("burst while walking"), [](AMorphOperative* O) { O->CmdFire(true); });
	Add(22.0f, TEXT("reload while walking"), [](AMorphOperative* O) { O->CmdReload(); });
	Add(24.0f, TEXT("stop, directional cast"), [](AMorphOperative* O) { O->SetMoveInput(FVector2D::ZeroVector, 0.f); });
	Add(24.8f, TEXT("cast directional"), [](AMorphOperative* O) { O->CmdCast(0); });
	Add(26.0f, TEXT("cast ground"), [](AMorphOperative* O) { O->CmdCast(1); });
	Add(27.6f, TEXT("channel start (held)"), [](AMorphOperative* O) { O->CmdChannel(true); });
	Add(29.2f, TEXT("hit during channel -> interrupt"), [](AMorphOperative* O) { O->CmdHit(0); });
	Add(30.6f, TEXT("charge (held)"), [](AMorphOperative* O) { O->CmdCharge(true); });
	Add(32.0f, TEXT("charge release"), [](AMorphOperative* O) { O->CmdCharge(false); });
	Add(33.4f, TEXT("charge again"), [](AMorphOperative* O) { O->CmdCharge(true); });
	Add(34.2f, TEXT("charge cancel"), [](AMorphOperative* O) { O->CmdChargeCancel(); });
	Add(35.4f, TEXT("deploy beacon"), [](AMorphOperative* O) { O->CmdDeploy(); });
	Add(37.4f, TEXT("uplink (held to completion)"), [](AMorphOperative* O) { O->CmdUplink(true); });
	Add(41.2f, TEXT("uplink release"), [](AMorphOperative* O) { O->CmdUplink(false); });
	Add(41.6f, TEXT("blink"), [](AMorphOperative* O) { O->CmdBlink(); });
	Add(43.0f, TEXT("hit while running"), [](AMorphOperative* O) { O->SetMoveInput(FVector2D(-1.f, 0.f), 1.f); });
	Add(43.6f, TEXT("hit left"), [](AMorphOperative* O) { O->CmdHit(2); });
	Add(44.4f, TEXT("stop, stun"), [](AMorphOperative* O) { O->SetMoveInput(FVector2D::ZeroVector, 0.f); O->CmdStun(); });
	Add(49.0f, TEXT("knockback"), [](AMorphOperative* O) { O->CmdKnockback(); });
	Add(50.6f, TEXT("knockdown (hit from behind -> face down)"), [](AMorphOperative* O) { O->CmdKnockdown(false); });
	Add(57.0f, TEXT("knockup -> lands on back"), [](AMorphOperative* O) { O->CmdKnockup(); });
	Add(64.0f, TEXT("sleep"), [](AMorphOperative* O) { O->CmdSleep(); });
	Add(67.0f, TEXT("wake"), [](AMorphOperative* O) { O->CmdSleep(); });
	Add(69.0f, TEXT("cast self, death during the cast"), [](AMorphOperative* O) { O->CmdCast(2); });
	Add(69.4f, TEXT("death (front impact) overrides the cast"), [](AMorphOperative* O) { O->CmdDeath(true); });
	Add(70.0f, TEXT("second death request is ignored"), [](AMorphOperative* O) { O->CmdDeath(false); });
	Add(73.0f, TEXT("respawn"), [](AMorphOperative* O) { O->CmdRespawn(); });
	Add(76.0f, TEXT("jump then death in the air"), [](AMorphOperative* O) { O->CmdJump(); });
	Add(76.5f, TEXT("death (back impact) while airborne"), [](AMorphOperative* O) { O->CmdDeath(false); });
	Add(80.0f, TEXT("respawn"), [](AMorphOperative* O) { O->CmdRespawn(); });
	Add(83.0f, TEXT("greet"), [](AMorphOperative* O) { O->CmdEmote(TEXT("greet")); });
	Add(85.0f, TEXT("dialogue with audio"), [](AMorphOperative* O) { O->CmdDialogue(); });
	Add(104.0f, TEXT("victory"), [](AMorphOperative* O) { O->CmdEmote(TEXT("victory")); });
	Add(107.5f, TEXT("end"), [](AMorphOperative* O) { O->CmdResetCharacter(); });
}

void AMorphShowcaseGameMode::StartSequence(bool bExitWhenDone)
{
	AMorphOperative* O = GetPlayerOperative();
	if (!O)
	{
		return;
	}
	BuildSequence();
	bSequence = true;
	bExitAfterSequence = bExitWhenDone;
	SeqTime = 0.f;
	SeqIndex = 0;
	TraceLines.Reset();
	O->SetActorLocation(SeqStartLoc);    // open ground: ~20 m of travel along +X stays clear of the room props
	O->SetActorRotation(FRotator::ZeroRotator);
	if (AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController()))
	{
		PC->bScripted = true;
	}
	SetFixedStep(1.f / 60.f);
	WriteTraceLine(TEXT("# MorphRig deterministic showcase sequence (fixed step 1/60 s)"));
	WriteTraceLine(TEXT("# time\tstate\tclip\ttrace\tspeed_cms\tlocation_cm"));
}

void AMorphShowcaseGameMode::StopSequence()
{
	if (!bSequence)
	{
		return;
	}
	bSequence = false;
	if (!IsCapturing())
	{
		SetFixedStep(0.f);
	}
	if (AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController()))
	{
		PC->bScripted = false;
	}
	FFileHelper::SaveStringArrayToFile(TraceLines, *TracePath);
	UE_LOG(LogMorphShowcase, Log, TEXT("sequence trace written: %s (%d lines)"), *TracePath, TraceLines.Num());
	if (bExitAfterSequence)
	{
		UKismetSystemLibrary::QuitGame(GetWorld(), nullptr, EQuitPreference::Quit, false);
	}
}

FString AMorphShowcaseGameMode::SequenceStatus() const
{
	if (!bSequence)
	{
		return FString();
	}
	const FString L = Steps.IsValidIndex(SeqIndex - 1) ? Steps[SeqIndex - 1].Label : TEXT("");
	return FString::Printf(TEXT("SEQUENCE %.1fs  step %d/%d: %s   (Esc stops)"), SeqTime, SeqIndex, Steps.Num(), *L);
}

void AMorphShowcaseGameMode::TickSequence(float Dt)
{
	if (!bSequence)
	{
		return;
	}
	AMorphOperative* O = GetPlayerOperative();
	SeqTime += Dt;
	while (O && SeqIndex < Steps.Num() && Steps[SeqIndex].Time <= SeqTime + 1e-4f)
	{
		WriteTraceLine(FString::Printf(TEXT("%8.3f\tSTEP\t%s"), SeqTime, *Steps[SeqIndex].Label));
		Steps[SeqIndex].Do(O);
		++SeqIndex;
	}
	if (SeqIndex >= Steps.Num() && SeqTime > Steps.Last().Time + 2.f)
	{
		StopSequence();
	}
}

// ===================================================================================== benchmark
void AMorphShowcaseGameMode::StartBenchmark(float Seconds, float Warmup, int32 NumInstances)
{
	SetInstanceCount(NumInstances);
	bBench = true;
	BenchSeconds = Seconds;
	BenchWarmup = Warmup;
	BenchClock = 0.f;
	FrameMs.Reset();
	GameMs.Reset();
	RenderMs.Reset();
	GpuMs.Reset();
	if (AMorphOperative* O = GetPlayerOperative())
	{
		O->SetAutoPilot(true, 99);
	}
	UE_LOG(LogMorphShowcase, Log, TEXT("benchmark: %d instances, warmup %.1fs, capture %.1fs"), NumInstances, Warmup,
	       Seconds);
}

FString AMorphShowcaseGameMode::BenchStatus() const
{
	if (!bBench)
	{
		return FString();
	}
	return FString::Printf(TEXT("BENCHMARK %s %.1f / %.1fs  (%d instances)"),
	                       BenchClock < BenchWarmup ? TEXT("warmup") : TEXT("capture"), BenchClock,
	                       BenchWarmup + BenchSeconds, GetInstanceCount());
}

void AMorphShowcaseGameMode::TickBenchmark(float Dt)
{
	if (!bBench)
	{
		return;
	}
	BenchClock += Dt;
	if (BenchClock < BenchWarmup)
	{
		return;
	}
	FrameMs.Add(FApp::GetDeltaTime() * 1000.f);
	GameMs.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));
	RenderMs.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));
	GpuMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()));
	if (BenchClock >= BenchWarmup + BenchSeconds)
	{
		FinishBenchmark();
	}
}

void AMorphShowcaseGameMode::FinishBenchmark()
{
	bBench = false;
	auto Stats = [](TArray<float> V) {
		V.Sort();
		const int32 N = V.Num();
		double Sum = 0.0;
		for (float x : V) Sum += x;
		auto P = [&V, N](double q) { return N ? V[FMath::Clamp(int32(q * (N - 1)), 0, N - 1)] : 0.f; };
		return FString::Printf(TEXT("{\"avg\": %.3f, \"p50\": %.3f, \"p95\": %.3f, \"p99\": %.3f, \"max\": %.3f}"),
		                       N ? Sum / N : 0.0, P(0.5), P(0.95), P(0.99), N ? V.Last() : 0.f);
	};
	double Sum = 0.0;
	for (float x : FrameMs) Sum += x;
	const double Avg = FrameMs.Num() ? Sum / FrameMs.Num() : 0.0;
	FIntPoint Res(0, 0);
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		Res = GEngine->GameViewport->Viewport->GetSizeXY();
	}
	const FPlatformMemoryConstants& Mem = FPlatformMemory::GetConstants();
	const FString Stamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
	const FString Base = FPaths::ProjectLogDir() / FString::Printf(TEXT("MorphRig_Perf_%dinst_%s"), GetInstanceCount(), *Stamp);
	TArray<FString> Csv;
	Csv.Add(TEXT("frame,frame_ms,game_ms,render_ms,gpu_ms"));
	for (int32 i = 0; i < FrameMs.Num(); ++i)
	{
		Csv.Add(FString::Printf(TEXT("%d,%.3f,%.3f,%.3f,%.3f"), i, FrameMs[i], GameMs[i], RenderMs[i], GpuMs[i]));
	}
	FFileHelper::SaveStringArrayToFile(Csv, *(Base + TEXT(".csv")));
	const FString Json = FString::Printf(
		TEXT("{\n  \"instances\": %d,\n  \"frames\": %d,\n  \"warmup_s\": %.1f,\n  \"capture_s\": %.1f,\n"
		     "  \"avg_fps\": %.1f,\n  \"frame_ms\": %s,\n  \"game_thread_ms\": %s,\n  \"render_thread_ms\": %s,\n"
		     "  \"gpu_ms\": %s,\n  \"resolution\": \"%dx%d\",\n  \"rhi\": \"%s\",\n  \"gpu\": \"%s\",\n"
		     "  \"gpu_driver\": \"%s\",\n  \"cpu\": \"%s\",\n  \"cpu_cores\": %d,\n  \"cpu_threads\": %d,\n"
		     "  \"ram_gb\": %u,\n  \"fixed_timestep\": %s,\n  \"vsync\": \"off\",\n  \"frame_generation\": \"none\"\n}\n"),
		GetInstanceCount(), FrameMs.Num(), BenchWarmup, BenchSeconds, Avg > 0 ? 1000.0 / Avg : 0.0, *Stats(FrameMs),
		*Stats(GameMs), *Stats(RenderMs), *Stats(GpuMs), Res.X, Res.Y, GDynamicRHI ? GDynamicRHI->GetName() : TEXT("?"),
		*GRHIAdapterName, *GRHIAdapterUserDriverVersion, *FPlatformMisc::GetCPUBrand(),
		FPlatformMisc::NumberOfCores(), FPlatformMisc::NumberOfCoresIncludingHyperthreads(), Mem.TotalPhysicalGB,
		FApp::UseFixedTimeStep() ? TEXT("true") : TEXT("false"));
	FFileHelper::SaveStringToFile(Json, *(Base + TEXT(".json")));
	UE_LOG(LogMorphShowcase, Log, TEXT("benchmark written: %s.json  avg %.2f ms (%.1f fps)"), *Base, Avg,
	       Avg > 0 ? 1000.0 / Avg : 0.0);
	if (FParse::Param(FCommandLine::Get(), TEXT("MorphExit")))
	{
		UKismetSystemLibrary::QuitGame(GetWorld(), nullptr, EQuitPreference::Quit, false);
	}
}

// ===================================================================================== capture
void AMorphShowcaseGameMode::StartCapture(const FString& Mode, const FString& Dir)
{
	CaptureMode = Mode;
	CaptureDir = Dir;
	CaptureFrame = 0;
	CaptureClock = 0.f;
	IFileManager::Get().MakeDirectory(*Dir, true);
	SetFixedStep(1.f / 30.f);
	AMorphOperative* O = GetPlayerOperative();
	AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController());
	if (PC)
	{
		PC->bScripted = true;
		PC->bCapture = true;
	}
	CaptureWarmup = 15;   // let the pose, camera interpolation and sky capture settle before frame 0
	if (Mode == TEXT("turntable"))
	{
		CaptureFrames = 30 * 10;
		FParse::Value(FCommandLine::Get(), TEXT("MorphCaptureFrames="), CaptureFrames);
		if (PC) PC->SetCamMode(EMorphCamera::Front);
		if (O) TurntableBaseYaw = O->GetMesh()->GetRelativeRotation().Yaw;
		if (O) O->CmdPreview(TEXT("idle_relaxed"), true);
	}
	else if (Mode == TEXT("face"))
	{
		CaptureFrames = 30 * 19;
		if (PC) PC->SetCamMode(EMorphCamera::Face);
	}
	else  // showcase: the deterministic sequence, cameras cut between views
	{
		CaptureFrames = 30 * 108;
		CaptureWarmup = 0;    // the sequence starts now; its first frame is captured
		StartSequence(false);
		SetFixedStep(1.f / 30.f);
		if (PC) PC->SetCamMode(EMorphCamera::ThirdPerson);
	}
	UE_LOG(LogMorphShowcase, Log, TEXT("capture %s: %d frames -> %s"), *Mode, CaptureFrames, *Dir);
}

void AMorphShowcaseGameMode::TickCapture(float Dt)
{
	if (CaptureMode.IsEmpty())
	{
		return;
	}
	AMorphOperative* O = GetPlayerOperative();
	AMorphPlayerController* PC = Cast<AMorphPlayerController>(GetWorld()->GetFirstPlayerController());
	if (CaptureWarmup > 0)
	{
		--CaptureWarmup;
		return;
	}
	CaptureClock += Dt;
	if (CaptureMode == TEXT("turntable") && O)
	{
		// the mesh turns on its spot (actor, camera boom and light stay fixed)
		FRotator R = O->GetMesh()->GetRelativeRotation();
		R.Yaw = TurntableBaseYaw + 360.f * CaptureFrame / float(CaptureFrames);
		O->GetMesh()->SetRelativeRotation(R);
	}
	else if (CaptureMode == TEXT("face") && O && CaptureFrame == 15)
	{
		O->CmdDialogue();
		UE_LOG(LogMorphShowcase, Log, TEXT("capture: dialogue starts at frame %d"), CaptureFrame);
	}
	else if (CaptureMode == TEXT("showcase") && PC)
	{
		const float T = CaptureClock;
		EMorphCamera Want = EMorphCamera::ThirdPerson;
		if (T > 24.f && T < 44.f) Want = EMorphCamera::Side;
		if (T > 44.f && T < 64.f) Want = EMorphCamera::TopDown;
		if (T > 64.f && T < 85.f) Want = EMorphCamera::Front;
		if (T > 85.f && T < 104.f) Want = EMorphCamera::Face;
		if (PC->GetCameraMode() != Want) PC->SetCamMode(Want);
	}
	const FString File = CaptureDir / FString::Printf(TEXT("%s_%05d.png"), *CaptureMode, CaptureFrame);
	FScreenshotRequest::RequestScreenshot(File, false, false);
	++CaptureFrame;
	if (CaptureFrame >= CaptureFrames)
	{
		UE_LOG(LogMorphShowcase, Log, TEXT("capture done: %d frames"), CaptureFrame);
		CaptureMode.Empty();
		if (bSequence) StopSequence();
		UKismetSystemLibrary::QuitGame(GetWorld(), nullptr, EQuitPreference::Quit, false);
	}
}
