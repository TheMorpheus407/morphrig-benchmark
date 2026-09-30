#include "ShowcaseRoom.h"
#include "OperativeLibrary.h"
#include "OperativeTypes.h"
#include "Components/StaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/PostProcessComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Kismet/GameplayStatics.h"

// ================================================================================================ target

AShowcaseTarget::AShowcaseTarget()
{
	PrimaryActorTick.bCanEverTick = true;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Ball = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ball"));
	Ball->SetupAttachment(Root);
	Stand = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Stand"));
	Stand->SetupAttachment(Root);
	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(Root);
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(16.f);
	Label->SetTextRenderColor(FColor(255, 240, 160));
	Label->SetCastShadow(false);
}

void AShowcaseTarget::Setup(UStaticMesh* Sphere, UStaticMesh* Cylinder, UMaterialInterface* Material, const FVector& InHome, float Height, int32 InIndex)
{
	Home = InHome;
	TargetHeight = Height;
	Index = InIndex;
	SetActorLocation(Home);
	Ball->SetStaticMesh(Sphere);
	Ball->SetRelativeLocation(FVector(0.f, 0.f, Height));
	Ball->SetRelativeScale3D(FVector(0.7f));
	Ball->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	Ball->SetMobility(EComponentMobility::Movable);
	Stand->SetStaticMesh(Cylinder);
	Stand->SetRelativeLocation(FVector(0.f, 0.f, Height * 0.5f - 18.f));
	Stand->SetRelativeScale3D(FVector(0.1f, 0.1f, Height / 100.f));
	Stand->SetCollisionProfileName(TEXT("BlockAll"));
	Stand->SetMobility(EComponentMobility::Movable);
	Label->SetRelativeLocation(FVector(0.f, 0.f, Height + 55.f));
	Label->SetText(FText::FromString(FString::Printf(TEXT("T%d  hits 0"), Index + 1)));
	if (Material)
	{
		BallMID = UMaterialInstanceDynamic::Create(Material, this);
		Ball->SetMaterial(0, BallMID);
		Stand->SetMaterial(0, Material);
	}
}

void AShowcaseTarget::RegisterHit(const FVector& Location)
{
	++HitCount;
	FlashTimer = 0.28f;
	Label->SetText(FText::FromString(FString::Printf(TEXT("T%d  hits %d"), Index + 1, HitCount)));
}

void AShowcaseTarget::SetPatrol(bool bOn, float Amplitude, float Speed)
{
	bPatrol = bOn;
	PatrolAmp = Amplitude;
	PatrolSpeed = Speed;
}

void AShowcaseTarget::MoveHome(const FVector& NewHome)
{
	Home = FVector(NewHome.X, NewHome.Y, Home.Z);
	SetActorLocation(Home);
}

void AShowcaseTarget::SetSelected(bool b)
{
	bSelected = b;
	Label->SetTextRenderColor(b ? FColor(120, 255, 160) : FColor(255, 240, 160));
}

void AShowcaseTarget::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bPatrol)
	{
		PatrolTime += DeltaSeconds * PatrolSpeed;
		SetActorLocation(Home + FVector(0.f, PatrolAmp * FMath::Sin(PatrolTime + Index * 0.9f), 0.f));
	}
	if (FlashTimer > 0.f)
	{
		FlashTimer = FMath::Max(0.f, FlashTimer - DeltaSeconds);
		const float U = FlashTimer / 0.28f;
		Ball->SetRelativeScale3D(FVector(0.7f * (1.f + 0.25f * U)));
		if (BallMID) BallMID->SetScalarParameterValue(TEXT("Flash"), U);
	}
	// text faces the camera
	if (const APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (PC->PlayerCameraManager)
		{
			const FVector ToCam = PC->PlayerCameraManager->GetCameraLocation() - Label->GetComponentLocation();
			Label->SetWorldRotation(FRotator(0.f, ToCam.Rotation().Yaw, 0.f));
		}
	}
}

// ================================================================================================ room

AShowcaseRoom::AShowcaseRoom()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

UStaticMeshComponent* AShowcaseRoom::AddBox(const FName& Name, const FVector& Center, const FVector& Size, const FRotator& Rot, UMaterialInterface* Mat, bool bShadow)
{
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this, FName(*FString::Printf(TEXT("%s_%d"), *Name.ToString(), CompCounter++)));
	C->SetStaticMesh(Cube);
	C->SetMobility(EComponentMobility::Movable);
	C->SetupAttachment(GetRootComponent());
	C->SetWorldLocationAndRotation(Center, Rot);
	C->SetWorldScale3D(Size / 100.f);
	C->SetCollisionProfileName(TEXT("BlockAll"));
	C->SetCastShadow(bShadow);
	if (Mat) C->SetMaterial(0, Mat);
	C->RegisterComponent();
	if (bBuildingProps) PropComps.Add(C);
	return C;
}

UStaticMeshComponent* AShowcaseRoom::AddCylinder(const FName& Name, const FVector& Center, float Radius, float Height, UMaterialInterface* Mat)
{
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this, FName(*FString::Printf(TEXT("%s_%d"), *Name.ToString(), CompCounter++)));
	C->SetStaticMesh(Cylinder);
	C->SetMobility(EComponentMobility::Movable);
	C->SetupAttachment(GetRootComponent());
	C->SetWorldLocation(Center);
	C->SetWorldScale3D(FVector(Radius / 50.f, Radius / 50.f, Height / 100.f));
	C->SetCollisionProfileName(TEXT("BlockAll"));
	if (Mat) C->SetMaterial(0, Mat);
	C->RegisterComponent();
	if (bBuildingProps) PropComps.Add(C);
	return C;
}

void AShowcaseRoom::AddLabel(const FString& Text, const FVector& Location, const FRotator& Rotation, float Size, FColor Color)
{
	UTextRenderComponent* T = NewObject<UTextRenderComponent>(this, FName(*FString::Printf(TEXT("Label_%d"), CompCounter++)));
	T->SetupAttachment(GetRootComponent());
	T->SetWorldLocationAndRotation(Location, Rotation);
	T->SetText(FText::FromString(Text));
	T->SetHorizontalAlignment(EHTA_Center);
	T->SetWorldSize(Size);
	T->SetTextRenderColor(Color);
	T->SetCastShadow(false);
	T->RegisterComponent();
	if (bBuildingProps) PropComps.Add(T);
	if (FMath::Abs(Rotation.Pitch) < 1.f) UprightLabels.Add(T);
}

void AShowcaseRoom::BeginPlay()
{
	Super::BeginPlay();
	const UOperativeLibrary* Lib = UOperativeLibrary::Get(this);
	Assets = Lib ? Lib->GetAssets() : nullptr;
	Cube = Assets ? Assets->CubeMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	Cylinder = Assets ? Assets->CylinderMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Assets)
	{
		if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("Floor"))) FloorMat = *M;
		if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("Wall"))) WallMat = *M;
		if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("Prop"))) PropMat = *M;
		if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("StudioFloor"))) StudioFloorMat = *M;
		if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("StudioWall"))) StudioWallMat = *M;
	}
	BuildGeometry();
	BuildLights();
}

void AShowcaseRoom::BuildGeometry()
{
	if (!Cube) return;
	const float Half = 1500.f;
	// floor: top surface at z = 0
	FloorComp = AddBox("Floor", FVector(0.f, 0.f, -10.f), FVector(2 * Half, 2 * Half, 20.f), FRotator::ZeroRotator, FloorMat);
	// walls
	const float WallH = 700.f;
	WallComps.Add(AddBox("WallN", FVector(Half + 25.f, 0.f, WallH * 0.5f), FVector(50.f, 2 * Half + 100.f, WallH), FRotator::ZeroRotator, WallMat ? WallMat.Get() : FloorMat.Get(), false));
	WallComps.Add(AddBox("WallS", FVector(-Half - 25.f, 0.f, WallH * 0.5f), FVector(50.f, 2 * Half + 100.f, WallH), FRotator::ZeroRotator, WallMat ? WallMat.Get() : FloorMat.Get(), false));
	WallComps.Add(AddBox("WallE", FVector(0.f, Half + 25.f, WallH * 0.5f), FVector(2 * Half + 100.f, 50.f, WallH), FRotator::ZeroRotator, WallMat ? WallMat.Get() : FloorMat.Get(), false));
	WallComps.Add(AddBox("WallW", FVector(0.f, -Half - 25.f, WallH * 0.5f), FVector(2 * Half + 100.f, 50.f, WallH), FRotator::ZeroRotator, WallMat ? WallMat.Get() : FloorMat.Get(), false));
	// the ground goes on beyond the walls (its top is 2 cm lower, the world-space grid of the floor material stays seamless): the top-down camera
	// looks over the hidden walls and sees floor instead of the dark dome
	if (UStaticMeshComponent* Outer = AddBox("OuterFloor", FVector(0.f, 0.f, -12.f), FVector(20000.f, 20000.f, 20.f), FRotator::ZeroRotator, FloorMat, false))
	{
		Outer->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
	// studio backdrop: a seamless cylinder around the floor (visible from inside only in studio mode)
	if (Cylinder)
	{
		StudioBackdrop = NewObject<UStaticMeshComponent>(this, TEXT("StudioBackdrop"));
		StudioBackdrop->SetStaticMesh(Cylinder);
		StudioBackdrop->SetMobility(EComponentMobility::Movable);
		StudioBackdrop->SetupAttachment(GetRootComponent());
		StudioBackdrop->SetWorldLocation(FVector(0.f, 0.f, 350.f));
		StudioBackdrop->SetWorldScale3D(FVector(Half / 50.f * 0.98f, Half / 50.f * 0.98f, 7.f));
		StudioBackdrop->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		StudioBackdrop->SetCastShadow(false);
		if (StudioWallMat) StudioBackdrop->SetMaterial(0, StudioWallMat);
		StudioBackdrop->SetVisibility(false);
		StudioBackdrop->RegisterComponent();
	}
	// a far dome of the studio material: views over the walls (top-down camera, a jump from the platform) show a dark gradient and never the empty black sky
	if (UStaticMesh* Sph = Assets ? Assets->SphereMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")))
	{
		HorizonDome = NewObject<UStaticMeshComponent>(this, TEXT("HorizonDome"));
		HorizonDome->SetStaticMesh(Sph);
		HorizonDome->SetMobility(EComponentMobility::Movable);
		HorizonDome->SetupAttachment(GetRootComponent());
		HorizonDome->SetWorldLocation(FVector::ZeroVector);
		HorizonDome->SetWorldScale3D(FVector(500.f));
		HorizonDome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		HorizonDome->SetCastShadow(false);
		if (StudioWallMat) HorizonDome->SetMaterial(0, StudioWallMat);
		HorizonDome->RegisterComponent();
	}
	bBuildingProps = true;

	// 20 degree ramp rising along +X to a 300 cm platform (drop from the platform demonstrates fall and heavy landing)
	{
		const float Angle = 20.f;
		const float Height = PlatformTop.Z;
		const float Len = Height / FMath::Sin(FMath::DegreesToRadians(Angle));
		const float Width = 300.f, Thick = 40.f;
		const FVector Dir(FMath::Cos(FMath::DegreesToRadians(Angle)), 0.f, FMath::Sin(FMath::DegreesToRadians(Angle)));
		const FVector Normal(-FMath::Sin(FMath::DegreesToRadians(Angle)), 0.f, FMath::Cos(FMath::DegreesToRadians(Angle)));
		const FVector TopCentre = FVector(RampBottom.X, RampBottom.Y, 0.f) + Dir * (Len * 0.5f);
		AddBox("Ramp", TopCentre - Normal * (Thick * 0.5f), FVector(Len, Width, Thick), FRotator(Angle, 0.f, 0.f), FloorMat);
		const float TopX = RampBottom.X + Len * FMath::Cos(FMath::DegreesToRadians(Angle));
		// platform: from the ramp top to X = PlatformTop.X + 200
		const float PlatLen = 500.f;
		AddBox("Platform", FVector(TopX + PlatLen * 0.5f - 15.f, RampBottom.Y, Height * 0.5f), FVector(PlatLen, Width + 100.f, Height), FRotator::ZeroRotator, FloorMat);
		PlatformTop = FVector(TopX + PlatLen * 0.5f, RampBottom.Y, Height);
		AddLabel(TEXT("RAMP 20 deg  >  300 cm platform (drop: heavy landing)"), FVector(RampBottom.X + 260.f, RampBottom.Y - 190.f, 30.f), FRotator(0.f, 90.f, 0.f), 22.f, FColor(200, 220, 255));
	}
	// stairs: five risers of 20 cm (the capsule step height) leading to a 100 cm platform
	{
		const float Riser = OperativeConst::StepHeight;
		const float Tread = 45.f;
		for (int32 I = 0; I < 5; ++I)
		{
			const float H = Riser * (I + 1);
			AddBox("Stair", FVector(StairsBottom.X + Tread * (I + 0.5f), StairsBottom.Y, H * 0.5f), FVector(Tread, 260.f, H), FRotator::ZeroRotator, FloorMat);
		}
		AddBox("StairTop", FVector(StairsBottom.X + Tread * 5.f + 120.f, StairsBottom.Y, Riser * 5.f * 0.5f), FVector(240.f, 260.f, Riser * 5.f), FRotator::ZeroRotator, FloorMat);
		AddLabel(TEXT("STEPS 5 x 20 cm"), FVector(StairsBottom.X - 60.f, StairsBottom.Y, 60.f), FRotator(0.f, 180.f, 0.f), 22.f, FColor(200, 220, 255));
	}
	// single steps of 10, 15 and 20 cm
	{
		const float Heights[3] = { 10.f, 15.f, 20.f };
		for (int32 I = 0; I < 3; ++I)
		{
			AddBox("Curb", FVector(SmallStepsStart.X + 340.f * I + 110.f, SmallStepsStart.Y, Heights[I] * 0.5f), FVector(180.f, 300.f, Heights[I]), FRotator::ZeroRotator, FloorMat);
		}
		AddLabel(TEXT("STEPS 10 / 15 / 20 cm"), FVector(SmallStepsStart.X + 450.f, SmallStepsStart.Y + 190.f, 30.f), FRotator(0.f, -90.f, 0.f), 22.f, FColor(200, 220, 255));
	}
	// prop contact station: table with cell holder and beacon dock
	{
		AddBox("StationTable", PropStation + FVector(0.f, 0.f, 42.f), FVector(70.f, 150.f, 84.f), FRotator::ZeroRotator, PropMat ? PropMat.Get() : FloorMat.Get());
		AddBox("StationTop", PropStation + FVector(0.f, 0.f, 88.f), FVector(80.f, 160.f, 6.f), FRotator::ZeroRotator, PropMat ? PropMat.Get() : FloorMat.Get());
		AddCylinder("CellHolder", PropStation + FVector(0.f, -45.f, 100.f), 5.f, 14.f, PropMat ? PropMat.Get() : FloorMat.Get());
		AddCylinder("BeaconDock", PropStation + FVector(0.f, 40.f, 94.f), 14.f, 6.f, PropMat ? PropMat.Get() : FloorMat.Get());
		AddLabel(TEXT("PROP STATION  (reload / deploy: hands on cell and beacon, Del = hands view)"), PropStation + FVector(-45.f, 0.f, 150.f), FRotator(0.f, 180.f, 0.f), 14.f, FColor(255, 220, 160));
	}
	// motion viewer pedestal
	{
		AddCylinder("ViewerPedestal", ViewerPedestal + FVector(0.f, 0.f, 6.f), 110.f, 12.f, FloorMat);
		// the backdrop stands in the lane of the curb course: it only exists while the motion viewer is open (the side camera would swing around it)
		ViewerBackdropComp = AddBox("ViewerBackdrop", ViewerPedestal + FVector(-260.f, 0.f, 200.f), FVector(20.f, 520.f, 400.f), FRotator::ZeroRotator, WallMat ? WallMat.Get() : FloorMat.Get(), false);
		PropComps.Remove(ViewerBackdropComp);
		SetViewerBackdropShown(false);
		AddLabel(TEXT("MOTION VIEWER  (key M: character to the pedestal, browser panel plays any clip)"), ViewerPedestal + FVector(-240.f, 0.f, 380.f), FRotator(0.f, 0.f, 0.f), 18.f, FColor(160, 255, 200));
	}
	// aim targets ahead of the start
	{
		const FVector Homes[5] = { FVector(900.f, -500.f, 0.f), FVector(1000.f, -170.f, 0.f), FVector(1100.f, 170.f, 0.f), FVector(950.f, 500.f, 0.f), FVector(1250.f, 0.f, 0.f) };
		const float Heights[5] = { 120.f, 60.f, 150.f, 100.f, 190.f };
		UStaticMesh* Sph = Assets ? Assets->SphereMesh.Get() : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
		UMaterialInterface* TMat = nullptr;
		if (Assets)
		{
			if (const TObjectPtr<UMaterialInterface>* M = Assets->ExtraMaterials.Find(FName("Target"))) TMat = *M;
		}
		for (int32 I = 0; I < 5; ++I)
		{
			AShowcaseTarget* T = GetWorld()->SpawnActor<AShowcaseTarget>(Homes[I], FRotator::ZeroRotator);
			if (!T) continue;
			T->Setup(Sph, Cylinder, TMat, Homes[I], Heights[I], I);
			Targets.Add(T);
		}
		if (Targets.Num() > 0) Targets[0]->SetSelected(true);
	}
	AddLabel(TEXT("MORPHRIG SHOWCASE  -  start"), FVector(-160.f, 0.f, 4.f), FRotator(90.f, 0.f, 0.f), 26.f, FColor(255, 255, 255));
	bBuildingProps = false;
}

void AShowcaseRoom::BuildLights()
{
	auto MakeLight = [this](const TCHAR* Name, float Intensity, const FLinearColor& Color, bool bShadows, int32 Priority) -> UDirectionalLightComponent*
	{
		UDirectionalLightComponent* L = NewObject<UDirectionalLightComponent>(this, Name);
		L->SetupAttachment(GetRootComponent());
		L->SetMobility(EComponentMobility::Movable);
		L->ForwardShadingPriority = Priority;
		L->SetIntensity(Intensity);
		L->SetLightColor(Color);
		L->SetCastShadows(bShadows);
		L->RegisterComponent();
		return L;
	};
	// the rotations follow the camera yaw (UpdateLightRig); only the key light casts shadows
	KeyLight = MakeLight(TEXT("KeyLight"), 6.0f, FLinearColor(1.f, 0.96f, 0.90f), true, 2);
	KeyLight->SetLightSourceAngle(2.5f);          // a wider source gives soft shadow edges (the default 0.5 degrees leaves a hard, ragged edge)
	FillLight = MakeLight(TEXT("FillLight"), 1.8f, FLinearColor(0.80f, 0.90f, 1.f), false, 1);
	RimLight = MakeLight(TEXT("RimLight"), 4.0f, FLinearColor(0.85f, 0.93f, 1.f), false, 0);
	UpdateLightRig(0.f);
	{
		USkyLightComponent* S = NewObject<USkyLightComponent>(this, TEXT("SkyLight"));
		S->SetupAttachment(GetRootComponent());
		S->SetMobility(EComponentMobility::Movable);
		S->SourceType = SLS_CapturedScene;
		S->bLowerHemisphereIsBlack = false;
		S->SetIntensity(1.3f);
		S->RegisterComponent();
		S->RecaptureSky();
	}
	// fixed exposure so the neutral floor stays the same in every view
	{
		UPostProcessComponent* PP = NewObject<UPostProcessComponent>(this, TEXT("PostProcess"));
		PP->SetupAttachment(GetRootComponent());
		PP->bUnbound = true;
		PP->BlendWeight = 1.f;
		FPostProcessSettings& S = PP->Settings;
		S.bOverride_AutoExposureMethod = true;
		S.AutoExposureMethod = AEM_Manual;
		S.bOverride_AutoExposureBias = true;
		S.AutoExposureBias = 9.5f;
		S.bOverride_BloomIntensity = true;
		S.BloomIntensity = 0.15f;
		S.bOverride_VignetteIntensity = true;
		S.VignetteIntensity = 0.f;
		PP->RegisterComponent();
	}
}

void AShowcaseRoom::UpdateLightRig(float CameraYaw)
{
	AppliedLightYaw = CameraYaw;
	// a directional light travels along its forward vector: a source at the upper left of the camera travels towards the right
	if (KeyLight) KeyLight->SetWorldRotation(bFaceLighting ? FRotator(-32.f, CameraYaw + 12.f, 0.f) : FRotator(-42.f, CameraYaw + 32.f, 0.f));
	if (KeyLight) KeyLight->SetShadowAmount(bFaceLighting ? 0.75f : 1.f);
	if (FillLight) FillLight->SetWorldRotation(bFaceLighting ? FRotator(-14.f, CameraYaw - 40.f, 0.f) : FRotator(-18.f, CameraYaw - 58.f, 0.f));
	if (FillLight) FillLight->SetIntensity(bFaceLighting ? 2.8f : 1.8f);
	if (RimLight) RimLight->SetWorldRotation(FRotator(-26.f, CameraYaw + 152.f, 0.f));   // from behind the subject, travelling back towards the camera
}

void AShowcaseRoom::SetViewerBackdropShown(bool bShow)
{
	if (!ViewerBackdropComp) return;
	ViewerBackdropComp->SetVisibility(bShow);
	ViewerBackdropComp->SetCollisionEnabled(bShow ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
}

void AShowcaseRoom::ApplyWallVisibility()
{
	for (UStaticMeshComponent* W : WallComps)
	{
		if (W) W->SetVisibility(!bStudio && !bWallsHiddenForView);
	}
}

void AShowcaseRoom::SetWallsHiddenForView(bool bHide)
{
	if (bWallsHiddenForView == bHide) return;
	bWallsHiddenForView = bHide;
	ApplyWallVisibility();
}

void AShowcaseRoom::SetFaceLighting(bool bOn)
{
	if (bFaceLighting == bOn) return;
	bFaceLighting = bOn;
	UpdateLightRig(AppliedLightYaw < 999.f ? AppliedLightYaw : 0.f);
}

void AShowcaseRoom::SetStudioMode(bool bOn)
{
	if (bStudio == bOn) return;
	bStudio = bOn;
	for (UPrimitiveComponent* C : PropComps)
	{
		if (!C) continue;
		C->SetVisibility(!bOn, true);
		C->SetCollisionEnabled(bOn ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics);
	}
	for (AShowcaseTarget* T : Targets)
	{
		if (!T) continue;
		T->SetActorHiddenInGame(bOn);
		T->SetActorEnableCollision(!bOn);
	}
	if (FloorComp) FloorComp->SetMaterial(0, bOn && StudioFloorMat ? StudioFloorMat.Get() : FloorMat.Get());
	// the corner walls give way to the seamless backdrop cylinder
	for (UStaticMeshComponent* W : WallComps)
	{
		if (!W) continue;
		W->SetCollisionEnabled(bOn ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics);
	}
	ApplyWallVisibility();
	if (StudioBackdrop) StudioBackdrop->SetVisibility(bOn && StudioWallMat != nullptr);
}

void AShowcaseRoom::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (const APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (PC->PlayerCameraManager)
		{
			const float Yaw = PC->PlayerCameraManager->GetCameraRotation().Yaw;
			if (FMath::Abs(FRotator::NormalizeAxis(Yaw - AppliedLightYaw)) > 0.5f) UpdateLightRig(Yaw);
			const FVector CamLoc = PC->PlayerCameraManager->GetCameraLocation();
			for (UTextRenderComponent* L : UprightLabels)
			{
				if (!L) continue;
				const FVector To = CamLoc - L->GetComponentLocation();
				L->SetWorldRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
			}
		}
	}
}

void AShowcaseRoom::SetTargetsPatrol(bool bOn)
{
	bTargetsPatrol = bOn;
	for (AShowcaseTarget* T : Targets) if (T) T->SetPatrol(bOn);
}

void AShowcaseRoom::SelectNextTarget()
{
	if (Targets.Num() == 0) return;
	if (Targets.IsValidIndex(SelectedTarget) && Targets[SelectedTarget]) Targets[SelectedTarget]->SetSelected(false);
	SelectedTarget = (SelectedTarget + 1) % Targets.Num();
	if (Targets[SelectedTarget]) Targets[SelectedTarget]->SetSelected(true);
}

void AShowcaseRoom::MoveSelectedTarget(const FVector& WorldPoint)
{
	if (AShowcaseTarget* T = GetSelectedTarget()) T->MoveHome(WorldPoint);
}

int32 AShowcaseRoom::TotalTargetHits() const
{
	int32 N = 0;
	for (const AShowcaseTarget* T : Targets) if (T) N += T->GetHitCount();
	return N;
}
