#include "ShowcaseFX.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "EngineUtils.h"
#include "Engine/World.h"

AShowcaseFX::AShowcaseFX()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

AShowcaseFX* AShowcaseFX::Get(UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	TActorIterator<AShowcaseFX> It(World);
	if (It)
	{
		return *It;
	}
	return World->SpawnActor<AShowcaseFX>();
}

UStaticMesh* AShowcaseFX::MeshFor(EShape Shape)
{
	static const TCHAR* Paths[4] = { TEXT("/Engine/BasicShapes/Sphere.Sphere"), TEXT("/Engine/BasicShapes/Cube.Cube"),
		TEXT("/Engine/BasicShapes/Cylinder.Cylinder"), TEXT("/Engine/BasicShapes/Plane.Plane") };
	if (!Meshes[Shape])
	{
		Meshes[Shape] = LoadObject<UStaticMesh>(nullptr, Paths[Shape]);
	}
	return Meshes[Shape];
}

AShowcaseFX::FItem& AShowcaseFX::Acquire(EShape Shape)
{
	if (!Material)
	{
		Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Showcase/M_FX.M_FX"));
	}
	FItem* Found = nullptr;
	for (FItem& I : Items)
	{
		if (!I.bActive)
		{
			Found = &I;
			break;
		}
	}
	if (!Found)
	{
		FItem& I = Items.AddDefaulted_GetRef();
		I.Comp = NewObject<UStaticMeshComponent>(this);
		I.Comp->SetMobility(EComponentMobility::Movable);
		I.Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		I.Comp->SetCastShadow(false);
		I.Comp->SetupAttachment(RootComponent);
		I.Comp->RegisterComponent();
		Components.Add(I.Comp);
		if (Material)
		{
			I.Mid = UMaterialInstanceDynamic::Create(Material, this);
			Mids.Add(I.Mid);
		}
		Found = &I;
	}
	Found->Comp->SetStaticMesh(MeshFor(Shape));
	if (Found->Mid)
	{
		Found->Comp->SetMaterial(0, Found->Mid);
	}
	Found->Comp->SetVisibility(true);
	Found->bActive = true;
	Found->Age = 0.f;
	Found->Key = NAME_None;
	Found->Velocity = FVector::ZeroVector;
	return *Found;
}

int32 AShowcaseFX::Spawn(EShape Shape, const FVector& Location, const FRotator& Rotation, const FVector& ScaleStart, const FVector& ScaleEnd,
	const FLinearColor& Color, float Duration, const FVector& Velocity, float Intensity, float OpacityStart, float OpacityEnd)
{
	FItem& I = Acquire(Shape);
	I.Comp->SetWorldLocationAndRotation(Location, Rotation);
	I.Comp->SetWorldScale3D(ScaleStart);
	I.ScaleStart = ScaleStart;
	I.ScaleEnd = ScaleEnd;
	I.Duration = FMath::Max(Duration, 0.01f);
	I.Velocity = Velocity;
	I.OpacityStart = OpacityStart;
	I.OpacityEnd = OpacityEnd;
	if (I.Mid)
	{
		I.Mid->SetVectorParameterValue(TEXT("Color"), Color);
		I.Mid->SetScalarParameterValue(TEXT("Intensity"), Intensity);
		I.Mid->SetScalarParameterValue(TEXT("Opacity"), OpacityStart);
	}
	return Items.Num();
}

void AShowcaseFX::SetPersistent(FName Key, EShape Shape, const FTransform& Transform, const FLinearColor& Color, float Intensity, float Opacity)
{
	FItem* Found = nullptr;
	for (FItem& I : Items)
	{
		if (I.bActive && I.Key == Key)
		{
			Found = &I;
			break;
		}
	}
	if (!Found)
	{
		Found = &Acquire(Shape);
		Found->Key = Key;
		Found->Duration = -1.f;
	}
	Found->Comp->SetWorldTransform(Transform);
	if (Found->Mid)
	{
		Found->Mid->SetVectorParameterValue(TEXT("Color"), Color);
		Found->Mid->SetScalarParameterValue(TEXT("Intensity"), Intensity);
		Found->Mid->SetScalarParameterValue(TEXT("Opacity"), Opacity);
	}
}

void AShowcaseFX::SetBeam(FName Key, const FVector& From, const FVector& To, float Radius, const FLinearColor& Color, float Intensity)
{
	const FVector Delta = To - From;
	const double Len = Delta.Size();
	if (Len < 1.0)
	{
		ClearPersistent(Key);
		return;
	}
	// the basic cylinder is 100 cm tall along Z with a 50 cm radius
	const FQuat Rot = FRotationMatrix::MakeFromZ(Delta / Len).ToQuat();
	SetPersistent(Key, Cylinder, FTransform(Rot, From + Delta * 0.5, FVector(Radius / 50.0, Radius / 50.0, Len / 100.0)), Color, Intensity, 0.75f);
}

void AShowcaseFX::ClearPersistent(FName Key)
{
	for (FItem& I : Items)
	{
		if (I.bActive && I.Key == Key)
		{
			I.bActive = false;
			I.Comp->SetVisibility(false);
		}
	}
}

void AShowcaseFX::ClearAll()
{
	for (FItem& I : Items)
	{
		I.bActive = false;
		I.Comp->SetVisibility(false);
	}
}

void AShowcaseFX::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	for (FItem& I : Items)
	{
		if (!I.bActive || I.Duration < 0.f)
		{
			continue;
		}
		I.Age += DeltaTime;
		const float A = FMath::Clamp(I.Age / I.Duration, 0.f, 1.f);
		if (A >= 1.f)
		{
			I.bActive = false;
			I.Comp->SetVisibility(false);
			continue;
		}
		I.Comp->AddWorldOffset(I.Velocity * DeltaTime);
		I.Comp->SetWorldScale3D(FMath::Lerp(I.ScaleStart, I.ScaleEnd, A));
		if (I.Mid)
		{
			I.Mid->SetScalarParameterValue(TEXT("Opacity"), FMath::Lerp(I.OpacityStart, I.OpacityEnd, A));
		}
	}
}
