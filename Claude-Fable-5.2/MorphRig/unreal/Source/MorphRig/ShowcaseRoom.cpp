#include "ShowcaseRoom.h"
#include "MorphRig.h"
#include "Components/StaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureCube.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"

AShowcaseRoom::AShowcaseRoom()
{
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

AShowcaseRoom* AShowcaseRoom::Get(UWorld* World)
{
	TActorIterator<AShowcaseRoom> It(World);
	if (It)
	{
		return *It;
	}
	return nullptr;
}

UStaticMeshComponent* AShowcaseRoom::AddShape(const TCHAR* Shape, const FVector& Location, const FRotator& Rotation, const FVector& Scale,
	const FLinearColor& Color, float Roughness, bool bCollision, const FLinearColor& Emissive, bool bGrid)
{
	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Engine/BasicShapes/%s.%s"), Shape, Shape));
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	C->SetupAttachment(RootComponent);
	C->SetWorldLocationAndRotation(Location, Rotation);
	C->SetWorldScale3D(Scale);
	C->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	C->SetCollisionObjectType(ECC_WorldStatic);
	C->SetCollisionResponseToAllChannels(ECR_Block);
	C->SetCanEverAffectNavigation(false);
	C->RegisterComponent();
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, bGrid ? TEXT("/Game/Showcase/M_Grid.M_Grid") : TEXT("/Game/Showcase/M_Solid.M_Solid"));
	if (Base)
	{
		UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(Base, this);
		if (!bGrid)
		{
			Mid->SetVectorParameterValue(TEXT("Color"), Color);
			Mid->SetScalarParameterValue(TEXT("Roughness"), Roughness);
			Mid->SetVectorParameterValue(TEXT("Emissive"), Emissive);
		}
		else
		{
			Mid->SetVectorParameterValue(TEXT("ColorA"), FLinearColor(0.105f, 0.108f, 0.115f));
			Mid->SetVectorParameterValue(TEXT("LineColor"), FLinearColor(0.21f, 0.215f, 0.225f));
		}
		C->SetMaterial(0, Mid);
		Mids.Add(Mid);
	}
	Parts.Add(C);
	return C;
}

void AShowcaseRoom::BeginPlay()
{
	Super::BeginPlay();
	const FLinearColor Concrete(0.16f, 0.165f, 0.175f), Light(0.24f, 0.245f, 0.255f), Dark(0.06f, 0.063f, 0.068f), Accent(0.55f, 0.33f, 0.07f);
	// floor (top at z = 0) and two backdrop walls
	AddShape(TEXT("Cube"), FVector(0, 0, -50), FRotator::ZeroRotator, FVector(HalfExtent * 2 / 100.f, HalfExtent * 2 / 100.f, 1.f), Concrete, 0.8f, true, FLinearColor::Black, true);
	AddShape(TEXT("Cube"), FVector(HalfExtent + 10, 0, 240), FRotator::ZeroRotator, FVector(0.2f, HalfExtent * 2 / 100.f, 4.8f), Dark, 0.9f);
	AddShape(TEXT("Cube"), FVector(0, HalfExtent + 10, 240), FRotator::ZeroRotator, FVector(HalfExtent * 2 / 100.f, 0.2f, 4.8f), Dark, 0.9f);

	// ramp and steps at the limits the character has to handle: 20 degree slope, nine 20 cm risers (rise 180 cm)
	const int32 NumSteps = 9;
	const float Rise = NumSteps * StepHeight;
	const float Run = Rise / FMath::Tan(FMath::DegreesToRadians(RampAngleDeg));
	const float SlopeLen = Run / FMath::Cos(FMath::DegreesToRadians(RampAngleDeg));
	const FVector Normal(-FMath::Sin(FMath::DegreesToRadians(RampAngleDeg)), 0, FMath::Cos(FMath::DegreesToRadians(RampAngleDeg)));
	const FVector MidTop(1000.f - Run * 0.5f, -550, Rise * 0.5f);
	AddShape(TEXT("Cube"), MidTop - Normal * 10.0, FRotator(RampAngleDeg, 0, 0), FVector(SlopeLen / 100.f, 3.f, 0.2f), Light, 0.7f);
	// platform joining ramp and steps
	AddShape(TEXT("Cube"), FVector(1150, -400, Rise * 0.5f), FRotator::ZeroRotator, FVector(3.f, 6.f, Rise / 100.f), Light, 0.7f);
	// steps descending from the platform
	const float Depth = 34.f;
	for (int32 i = 0; i < NumSteps - 1; ++i)
	{
		const float Top = Rise - (Rise / NumSteps) * (i + 1);
		AddShape(TEXT("Cube"), FVector(1000 - Depth * i - Depth * 0.5f, -250, Top * 0.5f), FRotator::ZeroRotator, FVector(Depth / 100.f, 3.f, Top / 100.f),
			(i % 2) ? Light : Concrete, 0.7f);
	}
	RampTop = FVector(1150, -550, Rise + 92);
	StepsTop = FVector(1150, -250, Rise + 92);
	StepsBottom = FVector(1000 - Depth * NumSteps - 120, -250, 92);

	// prop contact station: console pedestal with slanted panel and a deploy pad
	AddShape(TEXT("Cube"), FVector(-560, -520, 47), FRotator::ZeroRotator, FVector(0.9f, 0.4f, 0.94f), Dark, 0.5f);
	AddShape(TEXT("Cube"), FVector(-560, -505, 100), FRotator(0, 0, -28), FVector(0.86f, 0.36f, 0.05f), FLinearColor(0.05f, 0.06f, 0.07f), 0.3f, false, FLinearColor(0.0f, 0.5f, 0.8f) * 0.6f);
	AddShape(TEXT("Cylinder"), FVector(-560, -400, 1), FRotator::ZeroRotator, FVector(1.9f, 1.9f, 0.02f), Accent, 0.6f, false);
	StationPoint = FVector(-560, -420, 92);

	// motion viewer dais
	AddShape(TEXT("Cylinder"), FVector(-700, 600, 2), FRotator::ZeroRotator, FVector(3.2f, 3.2f, 0.04f), FLinearColor(0.16f, 0.17f, 0.19f), 0.6f, true);
	ViewerPoint = FVector(-700, 600, 96);

	// movable aim targets
	const FVector TargetPos[3] = { FVector(620, 320, 150), FVector(260, 760, 70), FVector(-180, 700, 235) };
	for (int32 i = 0; i < 3; ++i)
	{
		UStaticMeshComponent* Pole = AddShape(TEXT("Cylinder"), FVector::ZeroVector, FRotator::ZeroRotator, FVector(0.05f, 0.05f, 1.f), Dark, 0.6f, false);
		UStaticMeshComponent* Ball = AddShape(TEXT("Sphere"), TargetPos[i], FRotator::ZeroRotator, FVector(0.42f), FLinearColor(0.8f, 0.12f, 0.1f), 0.4f, false);
		TargetPoles.Add(Pole);
		Targets.Add(Ball);
		TargetMids.Add(Cast<UMaterialInstanceDynamic>(Ball->GetMaterial(0)));
		SetAimTargetLocation(i, TargetPos[i]);
	}

	// neutral backdrop dome (unlit vertical gradient, seen from inside)
	if (UStaticMesh* SphereMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")))
	{
		UStaticMeshComponent* Dome = NewObject<UStaticMeshComponent>(this);
		Dome->SetMobility(EComponentMobility::Movable);
		Dome->SetStaticMesh(SphereMesh);
		Dome->SetupAttachment(RootComponent);
		Dome->SetWorldScale3D(FVector(160.f));
		Dome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Dome->SetCastShadow(false);
		Dome->RegisterComponent();
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Showcase/M_Backdrop.M_Backdrop")))
		{
			Dome->SetMaterial(0, M);
		}
		Parts.Add(Dome);
	}

	// neutral lighting: key with shadows, two fills, sky ambient
	UWorld* W = GetWorld();
	auto AddSun = [&](const FRotator& Rot, bool bShadows, const FLinearColor& Color, int32 Priority)
	{
		ADirectionalLight* L = W->SpawnActor<ADirectionalLight>(FVector(0, 0, 800), Rot);
		if (L)
		{
			UDirectionalLightComponent* C = Cast<UDirectionalLightComponent>(L->GetLightComponent());
			C->SetMobility(EComponentMobility::Movable);
			C->SetLightColor(Color);
			C->SetCastShadows(bShadows);
			C->DynamicShadowDistanceMovableLight = 6000.f;
			C->SetForwardShadingPriority(Priority);
			C->SetAtmosphereSunLight(Priority > 0);
			Lights.Add(L);
		}
	};
	AddSun(KeyDefaultRot, true, FLinearColor(1.0f, 0.98f, 0.95f), 1);
	AddSun(FRotator(-30, -140, 0), false, FLinearColor(0.85f, 0.9f, 1.0f), 0);
	AddSun(FRotator(-25, 115, 0), false, FLinearColor(1.0f, 0.95f, 0.9f), 0);
	ASkyLight* Sky = W->SpawnActor<ASkyLight>(FVector(0, 0, 900), FRotator::ZeroRotator);
	if (Sky)
	{
		USkyLightComponent* SC = Sky->GetLightComponent();
		SC->SetMobility(EComponentMobility::Movable);
		if (UTextureCube* Cube = LoadObject<UTextureCube>(nullptr, TEXT("/Engine/EngineResources/GrayLightTextureCube.GrayLightTextureCube")))
		{
			SC->SourceType = SLS_SpecifiedCubemap;
			SC->Cubemap = Cube;
		}
		SC->bLowerHemisphereIsBlack = false;
		SC->SetCastShadows(false);
		Lights.Add(Sky);
	}
	SetLighting(1.9f, 0.32f, 0.22f, 0.3f);
}

void AShowcaseRoom::SetLighting(float Key, float FillA, float FillB, float Sky)
{
	KeyIntensity = Key;
	const float Values[4] = { Key * KeyScale, FillA, FillB, Sky };
	for (int32 i = 0; i < Lights.Num() && i < 4; ++i)
	{
		if (ADirectionalLight* DL = Cast<ADirectionalLight>(Lights[i]))
		{
			DL->GetLightComponent()->SetIntensity(Values[i]);
		}
		else if (ASkyLight* SL = Cast<ASkyLight>(Lights[i]))
		{
			SL->GetLightComponent()->SetIntensity(Values[i]);
			SL->GetLightComponent()->RecaptureSky();
		}
	}
}

void AShowcaseRoom::SetKeyDirection(const FRotator& Rot, float IntensityScale)
{
	KeyScale = IntensityScale;
	if (Lights.Num() > 0)
	{
		if (ADirectionalLight* DL = Cast<ADirectionalLight>(Lights[0]))
		{
			DL->SetActorRotation(Rot);
			DL->GetLightComponent()->SetIntensity(KeyIntensity * KeyScale);
		}
	}
}

void AShowcaseRoom::ResetKeyDirection()
{
	SetKeyDirection(KeyDefaultRot, 1.f);
}

void AShowcaseRoom::SetKeyShadow(float Amount, float SourceAngleDeg)
{
	if (Lights.Num() > 0)
	{
		if (ADirectionalLight* DL = Cast<ADirectionalLight>(Lights[0]))
		{
			if (UDirectionalLightComponent* C = Cast<UDirectionalLightComponent>(DL->GetLightComponent()))
			{
				C->SetShadowAmount(FMath::Clamp(Amount, 0.f, 1.f));
				C->SetLightSourceAngle(FMath::Clamp(SourceAngleDeg, 0.f, 30.f));
			}
		}
	}
}

FVector AShowcaseRoom::GetAimTargetLocation(int32 Index) const
{
	return Targets.IsValidIndex(Index) ? Targets[Index]->GetComponentLocation() : FVector::ZeroVector;
}

void AShowcaseRoom::SetAimTargetLocation(int32 Index, const FVector& Location)
{
	if (!Targets.IsValidIndex(Index))
	{
		return;
	}
	FVector P = Location;
	P.X = FMath::Clamp(P.X, -HalfExtent + 60.0, HalfExtent - 60.0);
	P.Y = FMath::Clamp(P.Y, -HalfExtent + 60.0, HalfExtent - 60.0);
	P.Z = FMath::Clamp(P.Z, 25.0, 420.0);
	Targets[Index]->SetWorldLocation(P);
	TargetPoles[Index]->SetWorldLocation(FVector(P.X, P.Y, P.Z * 0.5));
	TargetPoles[Index]->SetWorldScale3D(FVector(0.05, 0.05, P.Z / 100.0));
}

void AShowcaseRoom::HighlightTarget(int32 Index)
{
	for (int32 i = 0; i < TargetMids.Num(); ++i)
	{
		if (TargetMids[i])
		{
			TargetMids[i]->SetVectorParameterValue(TEXT("Emissive"), i == Index ? FLinearColor(2.5f, 0.5f, 0.1f) : FLinearColor::Black);
			TargetMids[i]->SetVectorParameterValue(TEXT("Color"), i == Index ? FLinearColor(1.0f, 0.4f, 0.1f) : FLinearColor(0.8f, 0.12f, 0.1f));
		}
	}
}

int32 AShowcaseRoom::FindTargetAt(const FVector& RayOrigin, const FVector& RayDir, float Tolerance) const
{
	int32 Best = INDEX_NONE;
	double BestDist = Tolerance;
	for (int32 i = 0; i < Targets.Num(); ++i)
	{
		const double D = FMath::PointDistToLine(Targets[i]->GetComponentLocation(), RayDir, RayOrigin);
		if (D < BestDist)
		{
			BestDist = D;
			Best = i;
		}
	}
	return Best;
}
