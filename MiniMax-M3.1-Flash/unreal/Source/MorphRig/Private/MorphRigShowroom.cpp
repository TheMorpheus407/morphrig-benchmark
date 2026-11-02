// MorphRig - the interactive demonstration room.
#include "MorphRigShowroom.h"

#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "MorphRigLog.h"
#include "UObject/ConstructorHelpers.h"

AMorphRigShowroom::AMorphRigShowroom()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

	KeyLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("KeyLight"));
	KeyLight->SetupAttachment(RootComponent);
	KeyLight->SetRelativeLocation(FVector(300.0f, -300.0f, 420.0f));
	KeyLight->SetIntensity(9000.0f);
	KeyLight->SetAttenuationRadius(3000.0f);
	KeyLight->SetLightColor(FLinearColor(0.85f, 0.90f, 1.0f));
	// The lights have to be movable.  A light with static mobility only
	// contributes through baked light maps, and this room is built at run
	// time and never baked, so a static light would light nothing at all.
	KeyLight->SetMobility(EComponentMobility::Movable);

	FillLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("FillLight"));
	FillLight->SetupAttachment(RootComponent);
	FillLight->SetRelativeLocation(FVector(-320.0f, -180.0f, 260.0f));
	FillLight->SetIntensity(3500.0f);
	FillLight->SetAttenuationRadius(2400.0f);
	FillLight->SetLightColor(FLinearColor(1.0f, 0.62f, 0.32f));
	FillLight->SetMobility(EComponentMobility::Movable);

	RimLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("RimLight"));
	RimLight->SetupAttachment(RootComponent);
	RimLight->SetRelativeLocation(FVector(0.0f, 380.0f, 320.0f));
	RimLight->SetIntensity(6000.0f);
	RimLight->SetAttenuationRadius(2600.0f);
	RimLight->SetLightColor(FLinearColor(0.35f, 0.75f, 1.0f));
	RimLight->SetMobility(EComponentMobility::Movable);
}

UStaticMeshComponent* AMorphRigShowroom::AddBox(const FVector& Location,
												 const FVector& Extent,
												 const FVector& Rotation,
												 UMaterialInterface* Material)
{
	UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(this);
	Comp->SetupAttachment(RootComponent);
	Comp->SetRelativeLocation(Location);
	Comp->SetRelativeRotation(FRotator(Rotation.X, Rotation.Y, Rotation.Z));
	// The engine cube is a hundred centimetres wide, so its half size is
	// fifty.  The scale therefore is the wanted half extent divided by
	// fifty.  Multiplying the extent by two instead would make every box
	// fifty times too thick and the floor would swallow the room.
	Comp->SetRelativeScale3D(Extent / 50.0f);
	Comp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Comp->SetCollisionResponseToAllChannels(ECR_Block);
	if (Material)
	{
		Comp->SetMaterial(0, Material);
	}
	AddInstanceComponent(Comp);
	Comp->RegisterComponent();
	return Comp;
}

UStaticMeshComponent* AMorphRigShowroom::AddCylinder(const FVector& Location,
													 float Radius, float Height,
													 UMaterialInterface* Material)
{
	UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(this);
	Comp->SetupAttachment(RootComponent);
	Comp->SetRelativeLocation(Location);
	// The cylinder of the engine is a hundred centimetres wide as well, so
	// the radius and the height are divided by fifty as well.
	Comp->SetRelativeScale3D(FVector(Radius * 2.0f / 50.0f, Radius * 2.0f / 50.0f,
									 Height / 50.0f));
	Comp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Comp->SetCollisionResponseToAllChannels(ECR_Block);
	if (Material)
	{
		Comp->SetMaterial(0, Material);
	}
	AddInstanceComponent(Comp);
	Comp->RegisterComponent();
	return Comp;
}

void AMorphRigShowroom::BeginPlay()
{
	Super::BeginPlay();

	// The room is built from the engine cube so the project needs no
	// external level asset.  A cubic mesh is loaded lazily; if it is not
	// available the room still spawns the lights and the targets.
	UStaticMesh* Cube = nullptr;
	FSoftObjectPath CubePath(TEXT("/Engine/BasicShapes/Cube.Cube"));
	Cube = Cast<UStaticMesh>(CubePath.TryLoad());

	UMaterialInterface* FloorMaterial =
		LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	UMaterialInterface* AccentMaterial =
		LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));

	if (Cube)
	{
		auto MakeCube = [this, Cube](const FVector& Location, const FVector& Extent,
									 const FVector& Rotation, UMaterialInterface* Material)
		{
			UStaticMeshComponent* Comp = AddBox(Location, Extent, Rotation, Material);
			Comp->SetStaticMesh(Cube);
			return Comp;
		};

		// floor
		MakeCube(FVector(0.0f, 0.0f, -10.0f), FVector(1500.0f, 1500.0f, 10.0f),
				 FVector::ZeroVector, FloorMaterial);
		// ramp
		UStaticMeshComponent* Ramp = MakeCube(FVector(600.0f, 300.0f, 40.0f),
											   FVector(200.0f, 150.0f, 8.0f),
											   FVector(0.0f, 14.0f, 0.0f), FloorMaterial);
		Ramp->SetMobility(EComponentMobility::Movable);
		// steps
		for (int32 i = 0; i < 4; ++i)
		{
			MakeCube(FVector(-700.0f, 250.0f, 8.0f + 16.0f * i),
					 FVector(150.0f, 150.0f, 8.0f), FVector::ZeroVector, FloorMaterial);
		}
		// prop contact station
		MakeCube(FVector(0.0f, 520.0f, 45.0f), FVector(120.0f, 60.0f, 45.0f),
				 FVector::ZeroVector, AccentMaterial);
		MakeCube(FVector(0.0f, 520.0f, 92.0f), FVector(130.0f, 70.0f, 4.0f),
				 FVector::ZeroVector, AccentMaterial);
		// movable aim targets
		const FVector TargetSpots[5] = {
			FVector(0.0f, -420.0f, 90.0f),
			FVector(240.0f, -420.0f, 140.0f),
			FVector(-240.0f, -420.0f, 140.0f),
			FVector(420.0f, -200.0f, 70.0f),
			FVector(-420.0f, -200.0f, 70.0f),
		};
		for (const FVector& Spot : TargetSpots)
		{
			UStaticMeshComponent* Target = MakeCube(Spot, FVector(35.0f, 8.0f, 35.0f),
													 FVector::ZeroVector, AccentMaterial);
			Target->SetMobility(EComponentMobility::Movable);
			Target->SetCustomDepthStencilValue(2);
			Targets.Add(Target);
		}
	}
	else
	{
		UE_LOG(LogMorphRig, Warning, TEXT("MorphRig: engine cube mesh unavailable"));
	}
}

TArray<FVector> AMorphRigShowroom::GetTargetLocations() const
{
	TArray<FVector> Result;
	for (const TObjectPtr<UStaticMeshComponent>& Target : Targets)
	{
		if (Target)
		{
			Result.Add(Target->GetComponentLocation());
		}
	}
	return Result;
}
