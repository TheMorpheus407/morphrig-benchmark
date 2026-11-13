#include "MorphRigGameMode.h"
#include "MorphRigCharacter.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigHUD.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/GameViewportClient.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/App.h"
#include "HAL/PlatformTime.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformMemory.h"
#include "RHI.h"
#include "IImageWrapperModule.h"
#include "IImageWrapper.h"
#include "Modules/ModuleManager.h"
#include "UnrealClient.h"
#include "RenderingThread.h"
#include "UObject/ConstructorHelpers.h"

AMorphRigGameMode::AMorphRigGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	DefaultPawnClass = nullptr; // We spawn PrimaryOperative explicitly and view through CameraRigActor
	HUDClass = AMorphRigHUD::StaticClass();

	// CDO hard references ensure BuildCookRun cooks /Engine/BasicShapes/* into the standalone Linux pak!
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeFinder.Succeeded()) { CachedCubeMesh = CubeFinder.Object; }

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (CylFinder.Succeeded()) { CachedCylinderMesh = CylFinder.Object; }

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereFinder(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereFinder.Succeeded()) { CachedSphereMesh = SphereFinder.Object; }

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MatFinder(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (MatFinder.Succeeded()) { CachedBasicShapeMat = MatFinder.Object; }
}

void AMorphRigGameMode::BeginPlay()
{
	Super::BeginPlay();

	BuildShowcaseRoom();

	UWorld* World = GetWorld();
	if (!World) { return; }

	// Spawn Primary Operative at origin (Capsule HalfHeight = 90 -> Z = 90 places soles at exact Z = 0.0!)
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	PrimaryOperative = World->SpawnActor<AMorphRigCharacter>(FVector(0.0f, 0.0f, 90.0f), FRotator::ZeroRotator, SpawnParams);
	if (PrimaryOperative)
	{
		PrimaryOperative->WorldAimTarget = AimTargetOrb ? AimTargetOrb->GetActorLocation() : FVector(320.0f, 0.0f, 145.0f);
		if (UMorphRigAnimInstance* AnimInst = PrimaryOperative->GetMorphRigAnim())
		{
			AnimInst->OnMarkerFired.AddUniqueDynamic(this, &AMorphRigGameMode::OnPrimaryMarkerLogged);
		}
	}

	// Spawn Camera Rig Actor + Offscreen Fallback SceneCapture2D
	CameraRigActor = World->SpawnActor<ACameraActor>(FVector(-280.0f, -120.0f, 145.0f), FRotator::ZeroRotator, SpawnParams);
	if (ACameraActor* CamAct = Cast<ACameraActor>(CameraRigActor))
	{
		CamAct->GetCameraComponent()->bConstrainAspectRatio = false;
		CamAct->GetCameraComponent()->SetFieldOfView(50.0f);
	}

	if (APlayerController* PC = World->GetFirstPlayerController())
	{
		PC->bShowMouseCursor = true;
		PC->bEnableClickEvents = true;
		PC->bEnableMouseOverEvents = true;
		if (CameraRigActor)
		{
			PC->SetViewTarget(CameraRigActor);
		}
	}

	SetCameraPreset(EMorphRigCameraPreset::OrbitClose);

	// Parse Command-Line Automation Flags (-AutoShowcase, -BenchmarkPerf, -CaptureVideo=..., -CaptureDir=...)
	const TCHAR* CmdLine = FCommandLine::Get();
	if (FParse::Param(CmdLine, TEXT("AutoShowcase")))
	{
		bAutoExitAfterShowcase = true;
		StartDeterministicShowcase();
	}
	if (FParse::Param(CmdLine, TEXT("BenchmarkPerf")))
	{
		bPerfBenchmarkMode = true;
		PerfPhase = 0;
		PerfFrameCounter = 0;
		LastWallTimeSec = FPlatformTime::Seconds();
		if (GEngine)
		{
			GEngine->bSmoothFrameRate = false;
			GEngine->Exec(World, TEXT("t.MaxFPS 0"));
			GEngine->Exec(World, TEXT("r.VSync 0"));
		}
		SetTenOperativesEnabled(false);
		SetCameraPreset(EMorphRigCameraPreset::PropStation);
	}
	if (FParse::Value(CmdLine, TEXT("CaptureVideo="), CaptureMode))
	{
		FParse::Value(CmdLine, TEXT("CaptureDir="), CaptureOutputDir);
		if (CaptureOutputDir.IsEmpty())
		{
			CaptureOutputDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("VideoFrames"));
		}
		IFileManager::Get().MakeDirectory(*CaptureOutputDir, true);

		// Lock deterministic 30 FPS fixed timestep for video capture
		FApp::SetUseFixedTimeStep(true);
		FApp::SetFixedDeltaTime(1.0 / 30.0);

		OffscreenCaptureRT = NewObject<UTextureRenderTarget2D>(this);
		OffscreenCaptureRT->RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8_SRGB;
		OffscreenCaptureRT->ClearColor = FLinearColor(0.08f, 0.09f, 0.11f, 1.0f);
		OffscreenCaptureRT->InitCustomFormat(1920, 1080, PF_B8G8R8A8, false);
		OffscreenCaptureRT->UpdateResourceImmediate(true);

		if (CameraRigActor)
		{
			OffscreenCaptureComp = NewObject<USceneCaptureComponent2D>(CameraRigActor);
			OffscreenCaptureComp->SetupAttachment(CameraRigActor->GetRootComponent());
			OffscreenCaptureComp->RegisterComponent();
			OffscreenCaptureComp->AttachToComponent(CameraRigActor->GetRootComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
			OffscreenCaptureComp->TextureTarget = OffscreenCaptureRT;
			OffscreenCaptureComp->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
			OffscreenCaptureComp->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_RenderScenePrimitives;
			OffscreenCaptureComp->bCaptureEveryFrame = false;
			OffscreenCaptureComp->bCaptureOnMovement = false;
			OffscreenCaptureComp->ShowFlags.SetAntiAliasing(true);
			OffscreenCaptureComp->ShowFlags.SetSkeletalMeshes(true);
			OffscreenCaptureComp->ShowFlags.SetLighting(true);
		}

		CaptureFrameIndex = -CaptureWarmupFrames;
		if (CaptureMode.Equals(TEXT("turntable"), ESearchCase::IgnoreCase))
		{
			CaptureTotalFrames = 360; // 12.0s @ 30 FPS
			bHideHUDForCapture = true;
			SetCameraPreset(EMorphRigCameraPreset::FullBodyFront);
			if (AimTargetOrb)
			{
				AimTargetOrb->SetActorHiddenInGame(true);
			}
			if (PrimaryOperative)
			{
				PrimaryOperative->WorldAimTarget = FVector(320.0f, 0.0f, 148.0f);
			}
		}
		else if (CaptureMode.Equals(TEXT("face"), ESearchCase::IgnoreCase))
		{
			CaptureTotalFrames = 504; // 16.8s @ 30 FPS (covers full 16.48s dialogue + settle)
			bHideHUDForCapture = false;
			SetCameraPreset(EMorphRigCameraPreset::FacialCloseUp);
			if (AimTargetOrb)
			{
				AimTargetOrb->SetActorHiddenInGame(true);
			}
		}
		else // "motion"
		{
			CaptureTotalFrames = 960; // 32.0s @ 30 FPS comprehensive motion/state/IK/10-instance showcase
			bHideHUDForCapture = false;
			SetCameraPreset(EMorphRigCameraPreset::OrbitClose);
		}

		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (AMorphRigHUD* MRHUD = Cast<AMorphRigHUD>(PC->GetHUD()))
			{
				MRHUD->bShowHUDPanels = !bHideHUDForCapture;
			}
		}
	}
}

void AMorphRigGameMode::BuildShowcaseRoom()
{
	UWorld* World = GetWorld();
	if (!World) { return; }

	UStaticMesh* CubeMesh = CachedCubeMesh ? CachedCubeMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UStaticMesh* CylMesh = CachedCylinderMesh ? CachedCylinderMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	UStaticMesh* SphereMesh = CachedSphereMesh ? CachedSphereMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	UMaterialInterface* BaseShapeMat = CachedBasicShapeMat ? CachedBasicShapeMat.Get() : LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));

	FActorSpawnParameters SP;
	SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// Helper to spawn clean neutral architectural static blocks (Cube is 100x100x100 cm)
	auto SpawnBlock = [&](const FVector& LocationCm, const FRotator& Rot, const FVector& SizeCm, const FLinearColor& Color, bool bCollide = true) -> AStaticMeshActor*
	{
		if (!CubeMesh) { return nullptr; }
		AStaticMeshActor* Act = World->SpawnActor<AStaticMeshActor>(LocationCm, Rot, SP);
		if (!Act) { return nullptr; }
		UStaticMeshComponent* SMC = Act->GetStaticMeshComponent();
		SMC->SetMobility(EComponentMobility::Movable);
		SMC->SetStaticMesh(CubeMesh);
		SMC->SetWorldScale3D(SizeCm / 100.0f);
		SMC->SetCollisionEnabled(bCollide ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
		SMC->SetCollisionResponseToAllChannels(ECR_Block);
		SMC->SetCastShadow(bCollide);
		if (BaseShapeMat)
		{
			UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseShapeMat, Act);
			MID->SetVectorParameterValue(TEXT("Color"), Color);
			SMC->SetMaterial(0, MID);
		}
		return Act;
	};

	// 1. Neutral Studio Floor (Z_top = 0.0 cm) + Subtle Origin Grid Strips & High-Clearance 360-Deg Cyclorama Studio Enclosure
	SpawnBlock(FVector(0.0f, 0.0f, -20.0f), FRotator::ZeroRotator, FVector(4000.0f, 4000.0f, 40.0f), FLinearColor(0.058f, 0.066f, 0.082f, 1.0f));
	for (int32 g = -8; g <= 8; ++g)
	{
		SpawnBlock(FVector(g * 200.0f, 0.0f, -0.2f), FRotator::ZeroRotator, FVector(2.5f, 3400.0f, 0.8f), FLinearColor(0.105f, 0.120f, 0.148f, 1.0f), false);
		SpawnBlock(FVector(0.0f, g * 200.0f, -0.2f), FRotator::ZeroRotator, FVector(3400.0f, 2.5f, 0.8f), FLinearColor(0.105f, 0.120f, 0.148f, 1.0f), false);
	}
	// Full 4-Wall Neutral Cyclorama Backdrop + High Overhead Studio Softbox Ceiling (Z = 2250 cm so all top-down cameras stay cleanly inside!)
	const FLinearColor WallCol(0.075f, 0.086f, 0.108f, 1.0f);
	SpawnBlock(FVector(-1850.0f,     0.0f, 1120.0f), FRotator::ZeroRotator, FVector(40.0f, 3800.0f, 2300.0f), WallCol, false);
	SpawnBlock(FVector(+1850.0f,     0.0f, 1120.0f), FRotator::ZeroRotator, FVector(40.0f, 3800.0f, 2300.0f), WallCol, false);
	SpawnBlock(FVector(    0.0f, -1850.0f, 1120.0f), FRotator::ZeroRotator, FVector(3800.0f, 40.0f, 2300.0f), WallCol, false);
	SpawnBlock(FVector(    0.0f, +1850.0f, 1120.0f), FRotator::ZeroRotator, FVector(3800.0f, 40.0f, 2300.0f), WallCol, false);
	SpawnBlock(FVector(    0.0f,     0.0f, 2250.0f), FRotator::ZeroRotator, FVector(3800.0f, 3800.0f, 40.0f), FLinearColor(0.45f, 0.49f, 0.57f, 1.0f), false);

	// 2. Motion Viewer Origin Ring (Cylinder is 100x100x100)
	if (CylMesh)
	{
		AStaticMeshActor* Ring = World->SpawnActor<AStaticMeshActor>(FVector(0.0f, 0.0f, -0.6f), FRotator::ZeroRotator, SP);
		if (Ring)
		{
			UStaticMeshComponent* RC = Ring->GetStaticMeshComponent();
			RC->SetMobility(EComponentMobility::Movable);
			RC->SetStaticMesh(CylMesh);
			RC->SetWorldScale3D(FVector(1.65f, 1.65f, 0.02f));
			RC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			if (BaseShapeMat)
			{
				UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseShapeMat, Ring);
				MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.0f, 0.45f, 0.62f, 1.0f));
				RC->SetMaterial(0, MID);
			}
		}
	}

	// 3. 18.5-Degree Slope Ramp (<= 20 deg per SPEC §9.7) + Top Deck at Y = -290 cm
	// Length = 380 cm tilted at +18.5 deg -> rises ~120.6 cm; sunk slightly so bottom feather meets Z = 0 cleanly!
	SpawnBlock(FVector(250.0f, -290.0f, 44.0f), FRotator(18.5f, 0.0f, 0.0f), FVector(390.0f, 200.0f, 24.0f), FLinearColor(0.18f, 0.21f, 0.26f, 1.0f));
	SpawnBlock(FVector(535.0f, -290.0f, 52.0f), FRotator::ZeroRotator, FVector(210.0f, 200.0f, 108.0f), FLinearColor(0.16f, 0.19f, 0.24f, 1.0f));

	// 4. Calibrated 10 cm, 15 cm, and 20 cm Steps (SPEC §9.7) at Y = +260 cm
	// Progressive Staircase: +10 cm -> +25 cm (+15 cm rise) -> +45 cm (+20 cm rise)
	SpawnBlock(FVector(150.0f, 260.0f,  5.0f), FRotator::ZeroRotator, FVector(110.0f, 180.0f, 10.0f), FLinearColor(0.19f, 0.22f, 0.27f, 1.0f));
	SpawnBlock(FVector(260.0f, 260.0f, 12.5f), FRotator::ZeroRotator, FVector(110.0f, 180.0f, 25.0f), FLinearColor(0.22f, 0.25f, 0.31f, 1.0f));
	SpawnBlock(FVector(380.0f, 260.0f, 22.5f), FRotator::ZeroRotator, FVector(130.0f, 180.0f, 45.0f), FLinearColor(0.25f, 0.28f, 0.35f, 1.0f));
	// Dedicated Split-Stance IK Step Pad (20.0 cm exact height at X=-140, Y=+160 so one foot stands on 20 cm, one on 0 cm!)
	SpawnBlock(FVector(-140.0f, 155.0f, 10.0f), FRotator::ZeroRotator, FVector(90.0f, 75.0f, 20.0f), FLinearColor(0.08f, 0.38f, 0.48f, 1.0f));

	// 5. Prop-Contact Inspection Station (X = +125 cm, Y = -125 cm)
	SpawnBlock(FVector(125.0f, -125.0f, 46.0f), FRotator::ZeroRotator, FVector(55.0f, 75.0f, 92.0f), FLinearColor(0.14f, 0.15f, 0.19f, 1.0f));
	SpawnBlock(FVector(125.0f, -112.0f, 96.0f), FRotator::ZeroRotator, FVector(10.0f, 10.0f, 8.0f), FLinearColor(0.0f, 0.85f, 1.0f, 1.0f), false);
	SpawnBlock(FVector(125.0f, -138.0f, 95.0f), FRotator::ZeroRotator, FVector(14.0f, 14.0f, 6.0f), FLinearColor(1.0f, 0.32f, 0.08f, 1.0f), false);

	// 6. Movable Glowing Aim Target Orb (placed slightly off-axis so front camera is never occluded)
	if (SphereMesh)
	{
		AStaticMeshActor* Orb = World->SpawnActor<AStaticMeshActor>(FVector(280.0f, -135.0f, 145.0f), FRotator::ZeroRotator, SP);
		if (Orb)
		{
			UStaticMeshComponent* SC = Orb->GetStaticMeshComponent();
			SC->SetMobility(EComponentMobility::Movable);
			SC->SetStaticMesh(SphereMesh);
			SC->SetWorldScale3D(FVector(0.24f, 0.24f, 0.24f));
			SC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			if (BaseShapeMat)
			{
				UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseShapeMat, Orb);
				MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.0f, 0.95f, 1.0f, 1.0f));
				SC->SetMaterial(0, MID);
			}
			AimTargetOrb = Orb;
		}
	}

	// 7. Balanced 360-Degree Studio Lighting + Non-Black Lower-Hemisphere SkyLight (clean face/eye/teeth/armor readability)
	TArray<AActor*> ExistingLights;
	UGameplayStatics::GetAllActorsOfClass(World, ADirectionalLight::StaticClass(), ExistingLights);
	if (ExistingLights.Num() == 0)
	{
		// Front-Right 3/4 Key Light (shines from +X, +Y, +Z onto front face, eyes, mouth & chest)
		if (ADirectionalLight* KeyLight = World->SpawnActor<ADirectionalLight>(FVector(0, 0, 500), FRotator(-26.0f, -146.0f, 0.0f), SP))
		{
			KeyLight->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			KeyLight->GetLightComponent()->SetIntensity(3.6f);
			KeyLight->GetLightComponent()->SetLightColor(FLinearColor(1.0f, 0.98f, 0.95f));
		}
		// Front-Left Eye/Mouth/Chest Soft Fill Light (eliminates harsh brow/chin/collar shadows)
		if (ADirectionalLight* FrontFill = World->SpawnActor<ADirectionalLight>(FVector(0, 0, 420), FRotator(-14.0f, 152.0f, 0.0f), SP))
		{
			FrontFill->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			FrontFill->GetLightComponent()->SetIntensity(2.5f);
			FrontFill->GetLightComponent()->SetLightColor(FLinearColor(0.88f, 0.94f, 1.0f));
			FrontFill->GetLightComponent()->SetCastShadows(false);
		}
		// Rear-Left & Rear-Right Studio Rim / Back Fill Lights (clean silhouette & 360 turntable readability)
		if (ADirectionalLight* RimLeft = World->SpawnActor<ADirectionalLight>(FVector(0, 0, 420), FRotator(-24.0f, 32.0f, 0.0f), SP))
		{
			RimLeft->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			RimLeft->GetLightComponent()->SetIntensity(2.6f);
			RimLeft->GetLightComponent()->SetLightColor(FLinearColor(0.86f, 0.94f, 1.0f));
			RimLeft->GetLightComponent()->SetCastShadows(false);
		}
		if (ADirectionalLight* RimRight = World->SpawnActor<ADirectionalLight>(FVector(0, 0, 420), FRotator(-24.0f, -34.0f, 0.0f), SP))
		{
			RimRight->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			RimRight->GetLightComponent()->SetIntensity(2.1f);
			RimRight->GetLightComponent()->SetLightColor(FLinearColor(0.95f, 0.92f, 0.88f));
			RimRight->GetLightComponent()->SetCastShadows(false);
		}
		// Subtle Upward Floor-Bounce Fill (illuminates jaw underside, upper teeth/palate, and armor bevels)
		if (ADirectionalLight* BounceFill = World->SpawnActor<ADirectionalLight>(FVector(0, 0, 120), FRotator(28.0f, 180.0f, 0.0f), SP))
		{
			BounceFill->GetLightComponent()->SetMobility(EComponentMobility::Movable);
			BounceFill->GetLightComponent()->SetIntensity(1.35f);
			BounceFill->GetLightComponent()->SetLightColor(FLinearColor(0.82f, 0.88f, 0.96f));
			BounceFill->GetLightComponent()->SetCastShadows(false);
		}
		if (ASkyLight* Sky = World->SpawnActor<ASkyLight>(FVector(0, 0, 320), FRotator::ZeroRotator, SP))
		{
			USkyLightComponent* SkyComp = Sky->GetLightComponent();
			SkyComp->SetMobility(EComponentMobility::Movable);
			SkyComp->bLowerHemisphereIsBlack = false;
			SkyComp->LowerHemisphereColor = FLinearColor(0.24f, 0.27f, 0.33f, 1.0f);
			SkyComp->SetIntensity(2.2f);
			SkyComp->RecaptureSky();
		}
		if (AExponentialHeightFog* Fog = World->SpawnActor<AExponentialHeightFog>(FVector(0, 0, 100), FRotator::ZeroRotator, SP))
		{
			Fog->GetComponent()->SetFogDensity(0.002f);
			Fog->GetComponent()->SetFogInscatteringColor(FLinearColor(0.07f, 0.08f, 0.11f));
		}
	}
}

void AMorphRigGameMode::SetCameraPreset(EMorphRigCameraPreset Preset)
{
	ActiveCameraPreset = Preset;
	switch (Preset)
	{
	case EMorphRigCameraPreset::OrbitClose:
		OrbitYawDeg = 154.0f;
		OrbitPitchDeg = -10.0f;
		OrbitDistance = 365.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
		CurrentCameraFOV = 54.0f;
		break;
	case EMorphRigCameraPreset::FullBodyFront:
		OrbitYawDeg = 180.0f;
		OrbitPitchDeg = -6.0f;
		OrbitDistance = 395.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
		CurrentCameraFOV = 54.0f;
		break;
	case EMorphRigCameraPreset::FullBodySide:
		OrbitYawDeg = 90.0f;
		OrbitPitchDeg = -6.0f;
		OrbitDistance = 395.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
		CurrentCameraFOV = 54.0f;
		break;
	case EMorphRigCameraPreset::TopDownMOBA:
		// 52-deg top-down action-game gameplay angle (SPEC §4 & §10)
		OrbitYawDeg = 180.0f;
		OrbitPitchDeg = -52.0f;
		OrbitDistance = 760.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
		CurrentCameraFOV = 56.0f;
		break;
	case EMorphRigCameraPreset::TopDown120Px:
		// Calibrated 52-deg top-down distance projecting 180 cm body height to ~120 pixels at 1920x1080!
		OrbitYawDeg = 180.0f;
		OrbitPitchDeg = -52.0f;
		OrbitDistance = 1850.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
		CurrentCameraFOV = 50.0f;
		break;
	case EMorphRigCameraPreset::FacialCloseUp:
		OrbitYawDeg = 172.0f;
		OrbitPitchDeg = -4.0f;
		OrbitDistance = 138.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 70.5f);
		CurrentCameraFOV = 42.0f;
		break;
	case EMorphRigCameraPreset::RampStepsIK:
		OrbitYawDeg = 135.0f;
		OrbitPitchDeg = -18.0f;
		OrbitDistance = 475.0f;
		OrbitPivotOffset = FVector(65.0f, 0.0f, 18.0f);
		CurrentCameraFOV = 56.0f;
		break;
	case EMorphRigCameraPreset::PropStation:
	default:
		OrbitYawDeg = 158.0f;
		OrbitPitchDeg = -24.0f;
		OrbitDistance = 640.0f;
		OrbitPivotOffset = FVector(0.0f, 0.0f, 10.0f);
		CurrentCameraFOV = 56.0f;
		break;
	}
}

void AMorphRigGameMode::UpdateCameraRig(float DeltaSeconds)
{
	if (!CameraRigActor || !PrimaryOperative)
	{
		return;
	}

	// Support smooth right-mouse drag camera orbit in interactive sessions
	if (CaptureMode.IsEmpty() && !bPerfBenchmarkMode)
	{
		if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
		{
			if (PC->IsInputKeyDown(EKeys::RightMouseButton))
			{
				float DX = 0.0f, DY = 0.0f;
				PC->GetInputMouseDelta(DX, DY);
				OrbitYawDeg += DX * 2.4f;
				OrbitPitchDeg = FMath::Clamp(OrbitPitchDeg + DY * 2.0f, -78.0f, 25.0f);
			}
		}
	}

	float EffectiveDistance = OrbitDistance;
	FVector BaseAnchor = PrimaryOperative->GetActorLocation();
	if (ActiveCameraPreset == EMorphRigCameraPreset::FacialCloseUp && PrimaryOperative->GetMesh())
	{
		const FVector HeadLoc = PrimaryOperative->GetMesh()->GetBoneLocation(TEXT("head"));
		if (!HeadLoc.IsNearlyZero())
		{
			BaseAnchor = HeadLoc - FVector(0.0f, 0.0f, 66.0f);
		}
	}
	else if (bTenOperativesActive && (ActiveCameraPreset == EMorphRigCameraPreset::TopDownMOBA || ActiveCameraPreset == EMorphRigCameraPreset::PropStation))
	{
		BaseAnchor = FVector(-265.0f, 0.0f, 95.0f);
		if (ActiveCameraPreset == EMorphRigCameraPreset::TopDownMOBA)
		{
			EffectiveDistance = FMath::Max(OrbitDistance, 920.0f);
		}
	}

	const FVector Pivot = BaseAnchor + OrbitPivotOffset;
	const FRotator OrbitRot(OrbitPitchDeg, OrbitYawDeg, 0.0f);
	const FVector CamPos = Pivot - OrbitRot.Vector() * EffectiveDistance;
	const FRotator LookRot = (Pivot - CamPos).Rotation();

	CameraRigActor->SetActorLocationAndRotation(CamPos, LookRot);
	if (ACameraActor* CamAct = Cast<ACameraActor>(CameraRigActor))
	{
		CamAct->GetCameraComponent()->SetFieldOfView(CurrentCameraFOV);
	}
	if (OffscreenCaptureComp)
	{
		OffscreenCaptureComp->SetWorldLocationAndRotation(CamPos, LookRot);
		OffscreenCaptureComp->FOVAngle = CurrentCameraFOV;
	}
}

void AMorphRigGameMode::SetTenOperativesEnabled(bool bEnableTen)
{
	if (bTenOperativesActive == bEnableTen)
	{
		return;
	}
	bTenOperativesActive = bEnableTen;

	for (AMorphRigCharacter* Extra : CrowdOperatives)
	{
		if (Extra) { Extra->Destroy(); }
	}
	CrowdOperatives.Reset();

	if (bTenOperativesActive && GetWorld())
	{
		// Spawn 9 additional simultaneous animated Operatives (total = 10!) alternating Team A & Team B
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		static const FVector Offsets[9] = {
			FVector(-160.0f, -220.0f, 90.0f), FVector(-160.0f, +220.0f, 90.0f),
			FVector(-310.0f, -340.0f, 90.0f), FVector(-310.0f, -115.0f, 90.0f),
			FVector(-310.0f, +115.0f, 90.0f), FVector(-310.0f, +340.0f, 90.0f),
			FVector(-470.0f, -240.0f, 90.0f), FVector(-470.0f,    0.0f, 90.0f),
			FVector(-470.0f, +240.0f, 90.0f)
		};
		for (int32 i = 0; i < 9; ++i)
		{
			if (AMorphRigCharacter* Inst = GetWorld()->SpawnActor<AMorphRigCharacter>(Offsets[i], FRotator::ZeroRotator, SP))
			{
				Inst->bIsCrowdInstance = true;
				Inst->CrowdRoleIndex = i;
				Inst->SetTeamVariant((i + 1) % 2, true);
				CrowdOperatives.Add(Inst);
			}
		}
	}
}

void AMorphRigGameMode::MoveAimTarget(const FVector& DeltaWorld)
{
	if (!AimTargetOrb) { return; }
	FVector Pos = AimTargetOrb->GetActorLocation() + DeltaWorld;
	Pos.X = FMath::Clamp(Pos.X, -500.0f, 700.0f);
	Pos.Y = FMath::Clamp(Pos.Y, -600.0f, 600.0f);
	Pos.Z = FMath::Clamp(Pos.Z, 20.0f, 290.0f);
	AimTargetOrb->SetActorLocation(Pos);
	if (PrimaryOperative)
	{
		PrimaryOperative->WorldAimTarget = Pos;
	}
}

void AMorphRigGameMode::OnPrimaryMarkerLogged(const FMorphRigEventRecord& Rec)
{
	if (bShowcaseRunning)
	{
		const FString Line = FString::Printf(TEXT("[t=%06.2fs] EVENT  layer=%-12s clip=%-18s marker=%-20s clip_t=%.2fs rate=%.2fx"),
			ShowcaseElapsed, *Rec.LayerName.ToString(), *Rec.ClipId.ToString(), *Rec.MarkerName.ToString(), Rec.ClipTimeSec, Rec.PlayRate);
		ShowcaseTraceLines.Add(Line);
		UE_LOG(LogTemp, Display, TEXT("[MorphRigShowcase] %s"), *Line);
	}
}

void AMorphRigGameMode::StartDeterministicShowcase()
{
	if (!PrimaryOperative) { return; }
	bShowcaseRunning = true;
	ShowcaseElapsed = 0.0f;
	ShowcaseStepIndex = -1;
	ShowcaseTraceLines.Reset();
	ShowcaseTraceLines.Add(TEXT("=== MORPHRIG DETERMINISTIC SHOWCASE SEQUENCE STATE & EVENT TRACE ==="));
	PrimaryOperative->ResetOperativeFull(FVector(0.0f, 0.0f, 90.0f), 0.0f);
}

void AMorphRigGameMode::StopDeterministicShowcase()
{
	if (!bShowcaseRunning) { return; }
	bShowcaseRunning = false;
	ShowcaseTraceLines.Add(FString::Printf(TEXT("=== SHOWCASE COMPLETE AT t=%.2fs (%d TRACE LINES) ==="), ShowcaseElapsed, ShowcaseTraceLines.Num()));
	WriteShowcaseTraceFile();
	if (PrimaryOperative)
	{
		PrimaryOperative->DesiredMoveInput = FVector2D::ZeroVector;
	}
	if (bAutoExitAfterShowcase)
	{
		FGenericPlatformMisc::RequestExit(false);
	}
}

void AMorphRigGameMode::TickDeterministicShowcase(float DeltaSeconds)
{
	if (!bShowcaseRunning || !PrimaryOperative) { return; }
	UMorphRigAnimInstance* Anim = PrimaryOperative->GetMorphRigAnim();
	if (!Anim) { return; }

	ShowcaseElapsed += DeltaSeconds;

	auto LogStep = [&](int32 StepId, const TCHAR* Desc)
	{
		if (ShowcaseStepIndex < StepId)
		{
			ShowcaseStepIndex = StepId;
			const FString Msg = FString::Printf(TEXT("[t=%06.2fs] STATE  Step %02d: %s"), ShowcaseElapsed, StepId, Desc);
			ShowcaseTraceLines.Add(Msg);
			UE_LOG(LogTemp, Display, TEXT("[MorphRigShowcase] %s"), *Msg);
		}
	};

	const float T = ShowcaseElapsed;
	if (T < 1.2f)
	{
		LogStep(1, TEXT("Combat Idle + Calibrated Upper-Body Aim Sweep (Yaw -45..+45, Pitch -25..+30)"));
		if (AimTargetOrb)
		{
			AimTargetOrb->SetActorLocation(FVector(280.0f, 220.0f * FMath::Sin(T * 4.5f), 135.0f + 95.0f * FMath::Cos(T * 4.5f)));
			PrimaryOperative->WorldAimTarget = AimTargetOrb->GetActorLocation();
		}
	}
	else if (T < 4.5f)
	{
		if (ShowcaseStepIndex < 2)
		{
			LogStep(2, TEXT("8-Dir Diagonal Strafe Run + Layered Ranged 3-Shot Burst + Additive Hit Without Foot Snap"));
			Anim->TriggerUpperBodyAction(EMorphRigUpperBodyMode::RangedBurst);
		}
		PrimaryOperative->SpeedTier = 1;
		const float Ang = (T - 1.2f) * 2.2f;
		PrimaryOperative->DesiredMoveInput = FVector2D(FMath::Cos(Ang), FMath::Sin(Ang));
		if (T > 2.8f && ShowcaseStepIndex < 3)
		{
			LogStep(3, TEXT("Additive Front Hit Reaction Layered Over Moving Gait + Forward Sprint"));
			Anim->TriggerAdditiveHit(TEXT("f"));
			PrimaryOperative->SpeedTier = 2;
		}
	}
	else if (T < 7.8f)
	{
		PrimaryOperative->DesiredMoveInput = FVector2D::ZeroVector;
		if (ShowcaseStepIndex < 4)
		{
			LogStep(4, TEXT("Melee 1 -> 2 -> 3 Forearm-Blade Combo Chain"));
			Anim->TriggerMeleeAttack();
		}
		else if (T > 5.0f && ShowcaseStepIndex < 5)
		{
			LogStep(5, TEXT("Queue Melee 2 Reverse Slash"));
			Anim->TriggerMeleeAttack();
		}
		else if (T > 5.7f && ShowcaseStepIndex < 6)
		{
			LogStep(6, TEXT("Queue Melee 3 Finisher Slash"));
			Anim->TriggerMeleeAttack();
		}
	}
	else if (T < 10.2f)
	{
		if (ShowcaseStepIndex < 7)
		{
			LogStep(7, TEXT("Physical Wrist-Emitter Power Cell Reload"));
			Anim->TriggerReload();
		}
	}
	else if (T < 13.0f)
	{
		if (ShowcaseStepIndex < 8)
		{
			LogStep(8, TEXT("Sustained Beam Channel Start -> Loop"));
			Anim->StartChannel(0.0f);
		}
		if (T > 11.7f && ShowcaseStepIndex < 9)
		{
			LogStep(9, TEXT("Arbitrary Midway Channel Interrupt (Pose-Snapshot Crossfade, No Frame-0 Snap!)"));
			Anim->InterruptChannel();
		}
	}
	else if (T < 15.8f)
	{
		if (ShowcaseStepIndex < 10)
		{
			LogStep(10, TEXT("Charge Windup -> Hold -> Forceful Release"));
			Anim->StartCharge();
		}
		if (T > 14.5f && ShowcaseStepIndex < 11)
		{
			LogStep(11, TEXT("Charge Release"));
			Anim->ReleaseCharge();
		}
	}
	else if (T < 18.8f)
	{
		if (ShowcaseStepIndex < 12)
		{
			LogStep(12, TEXT("Deploy Tactical Beacon Floor Contact + Root-Motion 2m Forward Dash + Event Blink"));
			Anim->TriggerDeploy();
		}
		if (T > 17.3f && ShowcaseStepIndex < 13)
		{
			LogStep(13, TEXT("Root-Motion Dash Forward (200 cm Capsule Displacement)"));
			Anim->TriggerDash(TEXT("f"));
		}
		if (T > 18.0f && ShowcaseStepIndex < 14)
		{
			LogStep(14, TEXT("Event-Driven Blink Out -> Teleport -> Blink In"));
			Anim->TriggerBlink();
		}
	}
	else if (T < 22.8f)
	{
		if (ShowcaseStepIndex < 15)
		{
			LogStep(15, TEXT("Ground-Adaptation Foot & Pelvis IK on 18.5-Deg Slope Ramp & 20 cm Step + 1.25x Fast Rate"));
			SetCameraPreset(EMorphRigCameraPreset::RampStepsIK);
			if (UCharacterMovementComponent* MC = PrimaryOperative->GetCharacterMovement()) { MC->StopMovementImmediately(); }
			PrimaryOperative->SetActorLocationAndRotation(FVector(10.0f, -290.0f, 90.5f), FRotator::ZeroRotator, false, nullptr, ETeleportType::TeleportPhysics);
			PrimaryOperative->DesiredFacingYaw = 0.0f;
			Anim->ActionPlayRate = 1.25f;
		}
		PrimaryOperative->SpeedTier = 0;
		PrimaryOperative->DesiredMoveInput = (T < 22.1f) ? FVector2D(1.0f, 0.0f) : FVector2D::ZeroVector;
	}
	else if (T < 28.0f)
	{
		PrimaryOperative->DesiredMoveInput = FVector2D::ZeroVector;
		Anim->ActionPlayRate = 1.0f;
		if (ShowcaseStepIndex < 16)
		{
			LogStep(16, TEXT("Knockdown Front -> Prone Front -> Plausible Getup Front"));
			SetCameraPreset(EMorphRigCameraPreset::OrbitClose);
			if (UCharacterMovementComponent* MC = PrimaryOperative->GetCharacterMovement()) { MC->StopMovementImmediately(); }
			PrimaryOperative->SetActorLocationAndRotation(FVector(0.0f, 0.0f, 90.0f), FRotator::ZeroRotator, false, nullptr, ETeleportType::TeleportPhysics);
			PrimaryOperative->DesiredFacingYaw = 0.0f;
			Anim->TriggerKnockdown(true, 0.7f);
		}
		if (T > 26.2f && ShowcaseStepIndex < 17)
		{
			LogStep(17, TEXT("Death Priority Override -> Connected Held Dead Pose"));
			Anim->TriggerDeath(false);
		}
	}
	else if (T < 31.8f)
	{
		if (ShowcaseStepIndex < 18)
		{
			LogStep(18, TEXT("Respawn Activation + Team B Crimson-Amber Variant + 52-Deg Top-Down & 10 Simultaneous Operatives"));
			Anim->TriggerRespawn();
			PrimaryOperative->SetTeamVariant(1, true);
			SetCameraPreset(EMorphRigCameraPreset::TopDownMOBA);
			SetTenOperativesEnabled(true);
		}
	}
	else
	{
		StopDeterministicShowcase();
	}
}

void AMorphRigGameMode::WriteShowcaseTraceFile() const
{
	const FString OutPath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Logs/MorphRig_ShowcaseTrace.log"));
	FFileHelper::SaveStringArrayToFile(ShowcaseTraceLines, *OutPath);
	UE_LOG(LogTemp, Display, TEXT("[MorphRig] Saved deterministic showcase trace to %s"), *OutPath);
}

void AMorphRigGameMode::TickPerformanceBenchmark()
{
	const double Now = FPlatformTime::Seconds();
	const double DtMs = (Now - LastWallTimeSec) * 1000.0;
	LastWallTimeSec = Now;

	PerfFrameCounter++;
	if (PerfPhase == 0)
	{
		if (PerfFrameCounter >= 360) { PerfPhase = 1; PerfFrameCounter = 0; }
	}
	else if (PerfPhase == 1)
	{
		PerfSamples1xMs.Add(DtMs);
		if (PrimaryOperative)
		{
			const FVector Drift = PrimaryOperative->GetActorLocation();
			if (Drift.Size2D() > 140.0f)
			{
				PrimaryOperative->DesiredMoveInput = FVector2D(-Drift.X, -Drift.Y).GetSafeNormal();
			}
			else
			{
				PrimaryOperative->DesiredMoveInput = FVector2D(FMath::Cos(PerfFrameCounter * 0.05f), FMath::Sin(PerfFrameCounter * 0.05f));
			}
		}
		if (PerfFrameCounter >= 240)
		{
			if (PrimaryOperative) { PrimaryOperative->ResetOperativeFull(FVector(0.0f, 0.0f, 90.0f), 0.0f); }
			SetTenOperativesEnabled(true);
			PerfPhase = 2;
			PerfFrameCounter = 0;
		}
	}
	else if (PerfPhase == 2)
	{
		if (PerfFrameCounter >= 150) { PerfPhase = 3; PerfFrameCounter = 0; }
	}
	else if (PerfPhase == 3)
	{
		PerfSamples10xMs.Add(DtMs);
		if (PerfFrameCounter >= 240)
		{
			WritePerformanceReportFile();
			bPerfBenchmarkMode = false;
			FGenericPlatformMisc::RequestExit(false);
		}
	}
}

void AMorphRigGameMode::WritePerformanceReportFile() const
{
	auto ComputeStats = [](TArray<double> Samples) -> FString
	{
		if (Samples.Num() == 0) { return TEXT("{}"); }
		Samples.Sort();
		double Sum = 0.0;
		for (double V : Samples) { Sum += V; }
		const double AvgMs = Sum / Samples.Num();
		const double AvgFPS = (AvgMs > 0.001) ? (1000.0 / AvgMs) : 0.0;
		const double P50 = Samples[FMath::Clamp(Samples.Num() / 2, 0, Samples.Num() - 1)];
		const double P95 = Samples[FMath::Clamp(FMath::FloorToInt(Samples.Num() * 0.95), 0, Samples.Num() - 1)];
		const double P99 = Samples[FMath::Clamp(FMath::FloorToInt(Samples.Num() * 0.99), 0, Samples.Num() - 1)];
		return FString::Printf(
			TEXT("{\"sample_frames\": %d, \"avg_frame_ms\": %.3f, \"avg_fps\": %.2f, \"p50_ms\": %.3f, \"p95_ms\": %.3f, \"p99_ms\": %.3f}"),
			Samples.Num(), AvgMs, AvgFPS, P50, P95, P99);
	};

	const FPlatformMemoryConstants& MemConst = FPlatformMemory::GetConstants();
	const double TotalRamGiB = static_cast<double>(MemConst.TotalPhysical) / (1024.0 * 1024.0 * 1024.0);
	const FString CpuBrand = FPlatformMisc::GetCPUBrand();
	const FString GpuBrand = GRHIAdapterName;
	const FString RhiName = GDynamicRHI ? GDynamicRHI->GetName() : TEXT("Vulkan");

	const FString JsonReport = FString::Printf(
		TEXT("{\n")
		TEXT("  \"resolution\": \"1920x1080\",\n")
		TEXT("  \"frame_generation\": false,\n")
		TEXT("  \"upscaling\": \"none (100%% native screen percentage)\",\n")
		TEXT("  \"render_settings\": \"Vulkan SM6, Cascaded Shadow Maps, Screen-Space Reflections, TAA, Bloom, Dynamic GI Off\",\n")
		TEXT("  \"active_features\": \"92-DEF skeleton, 46 morph targets, 8-dir phase-synced locomotion, cached 9-sample aim grid, upper-body layering, additive hit reactions, ground IK (20 deg slope / 20 cm step), damped secondary springs, LOD0/1/2\",\n")
		TEXT("  \"initial_warmup_frames\": 360,\n")
		TEXT("  \"crowd_warmup_frames\": 150,\n")
		TEXT("  \"cpu\": \"%s\",\n")
		TEXT("  \"gpu\": \"%s\",\n")
		TEXT("  \"rhi\": \"%s\",\n")
		TEXT("  \"ram_gib\": %.1f,\n")
		TEXT("  \"one_operative\": %s,\n")
		TEXT("  \"ten_simultaneous_operatives\": %s\n")
		TEXT("}\n"),
		*CpuBrand, *GpuBrand, *RhiName, TotalRamGiB,
		*ComputeStats(PerfSamples1xMs),
		*ComputeStats(PerfSamples10xMs));

	const FString OutPath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Logs/MorphRig_PerfReport.json"));
	FFileHelper::SaveStringToFile(JsonReport, *OutPath);
	UE_LOG(LogTemp, Display, TEXT("[MorphRigPerf]\n%s"), *JsonReport);
}

void AMorphRigGameMode::TickVideoCapture(float DeltaSeconds)
{
	if (CaptureMode.IsEmpty() || !PrimaryOperative)
	{
		return;
	}

	if (CaptureMode.Equals(TEXT("turntable"), ESearchCase::IgnoreCase))
	{
		if (CaptureFrameIndex >= 0)
		{
			const float U = static_cast<float>(CaptureFrameIndex) / static_cast<float>(FMath::Max(1, CaptureTotalFrames));
			OrbitYawDeg = 180.0f + U * 360.0f;
			OrbitPitchDeg = -6.0f;
			OrbitDistance = 395.0f;
			OrbitPivotOffset = FVector(0.0f, 0.0f, 0.0f);
			CurrentCameraFOV = 54.0f;
			// Show Team A Cyan for first 180 deg, Team B Crimson-Amber for second 180 deg!
			PrimaryOperative->SetTeamVariant((U < 0.5f) ? 0 : 1, false);
		}
	}
	else if (CaptureMode.Equals(TEXT("face"), ESearchCase::IgnoreCase))
	{
		if (CaptureFrameIndex == 0)
		{
			PrimaryOperative->SetTeamVariant(0, false);
			PrimaryOperative->TriggerDialoguePerformance();
		}
		if (CaptureFrameIndex >= 0)
		{
			const float T = CaptureFrameIndex / 30.0f;
			const float GestureWideAlpha = FMath::SmoothStep(6.2f, 7.0f, T) * (1.0f - FMath::SmoothStep(9.6f, 10.5f, T));
			// Expressive portrait framing showing head, eyes, mouth/teeth/tongue & smooth widen for wrist-console gesture
			OrbitYawDeg = 173.0f + 9.0f * FMath::Sin(T * 0.45f);
			OrbitPitchDeg = -4.0f;
			OrbitDistance = FMath::Lerp(138.0f, 184.0f, GestureWideAlpha);
			OrbitPivotOffset = FVector(0.0f, 0.0f, FMath::Lerp(70.5f, 56.0f, GestureWideAlpha));
			CurrentCameraFOV = 42.0f;
		}
	}
	else // "motion"
	{
		if (CaptureFrameIndex == 0 && !bShowcaseRunning)
		{
			StartDeterministicShowcase();
		}
	}

	UpdateCameraRig(DeltaSeconds);

	if (CaptureFrameIndex >= 0 && CaptureFrameIndex < CaptureTotalFrames)
	{
		const FString FramePath = FPaths::Combine(CaptureOutputDir, FString::Printf(TEXT("frame_%05d.png"), CaptureFrameIndex));
		SaveCapturedFramePNG(FramePath);
	}

	CaptureFrameIndex++;
	if (CaptureFrameIndex >= CaptureTotalFrames)
	{
		UE_LOG(LogTemp, Display, TEXT("[MorphRigCapture] Captured %d frames to %s"), CaptureTotalFrames, *CaptureOutputDir);
		FGenericPlatformMisc::RequestExit(false);
	}
}

void AMorphRigGameMode::SaveCapturedFramePNG(const FString& FilePath)
{
	TArray<FColor> Pixels;
	int32 Width = 1920, Height = 1080;
	bool bGotViewportPixels = false;
	const bool bIsOffscreenCmd = FParse::Param(FCommandLine::Get(), TEXT("RenderOffScreen"));

	// Only read GameViewport swapchain when running with an onscreen RHI swapchain
	if (!bIsOffscreenCmd && GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		FViewport* VP = GEngine->GameViewport->Viewport;
		if (VP->GetSizeXY().X > 0 && VP->GetSizeXY().Y > 0 && VP->GetRenderTargetTexture().IsValid())
		{
			FlushRenderingCommands();
			if (VP->ReadPixels(Pixels))
			{
				Width = VP->GetSizeXY().X;
				Height = VP->GetSizeXY().Y;
				for (int32 i = 0; i < Pixels.Num(); i += 64)
				{
					if (Pixels[i].R > 2 || Pixels[i].G > 2 || Pixels[i].B > 2)
					{
						bGotViewportPixels = true;
						break;
					}
				}
			}
		}
	}

	if (!bGotViewportPixels && OffscreenCaptureComp && OffscreenCaptureRT)
	{
		OffscreenCaptureComp->FOVAngle = CurrentCameraFOV;
		OffscreenCaptureComp->CaptureScene();

		if (!bHideHUDForCapture)
		{
			if (UWorld* World = GetWorld())
			{
				if (APlayerController* PC = World->GetFirstPlayerController())
				{
					if (AMorphRigHUD* MRHUD = Cast<AMorphRigHUD>(PC->GetHUD()))
					{
						UCanvas* OverlayCanvas = nullptr;
						FVector2D OverlaySize;
						FDrawToRenderTargetContext DrawCtx;
						UKismetRenderingLibrary::BeginDrawCanvasToRenderTarget(this, OffscreenCaptureRT, OverlayCanvas, OverlaySize, DrawCtx);
						if (OverlayCanvas)
						{
							MRHUD->RenderOffscreenTelemetry(OverlayCanvas);
						}
						UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, DrawCtx);
					}
				}
			}
		}

		FlushRenderingCommands();
		if (FTextureRenderTargetResource* RTRes = OffscreenCaptureRT->GameThread_GetRenderTargetResource())
		{
			FReadSurfaceDataFlags Flags(RCM_UNorm);
			Flags.SetLinearToGamma(false);
			RTRes->ReadPixels(Pixels, Flags);
			Width = OffscreenCaptureRT->SizeX;
			Height = OffscreenCaptureRT->SizeY;
		}
	}

	if (Pixels.Num() != Width * Height || Width <= 0 || Height <= 0)
	{
		return;
	}

	for (FColor& C : Pixels) { C.A = 255; }

	IImageWrapperModule& ImgMod = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	TSharedPtr<IImageWrapper> PngWrapper = ImgMod.CreateImageWrapper(EImageFormat::PNG);
	if (PngWrapper.IsValid() && PngWrapper->SetRaw(Pixels.GetData(), Pixels.Num() * sizeof(FColor), Width, Height, ERGBFormat::BGRA, 8))
	{
		const TArray64<uint8>& Compressed = PngWrapper->GetCompressed(85);
		FFileHelper::SaveArrayToFile(Compressed, *FilePath);
	}
}

void AMorphRigGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	SmoothedFrameMs = FMath::FInterpTo(SmoothedFrameMs, DeltaSeconds * 1000.0f, 0.12f, 1.0f);
	SmoothedFPS = (SmoothedFrameMs > 0.1f) ? (1000.0f / SmoothedFrameMs) : 60.0f;

	if (bShowcaseRunning)
	{
		TickDeterministicShowcase(DeltaSeconds);
	}
	if (bPerfBenchmarkMode)
	{
		TickPerformanceBenchmark();
	}
	if (!CaptureMode.IsEmpty())
	{
		TickVideoCapture(DeltaSeconds);
	}
	else
	{
		UpdateCameraRig(DeltaSeconds);
	}
}
