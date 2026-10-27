#include "MorphRoom.h"
#include "MorphRig.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureCube.h"
#include "PhysicsEngine/BodySetup.h"
#include "ProceduralMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

AMorphRoom::AMorphRoom()
{
    PrimaryActorTick.bCanEverTick = true;
    RoomRoot = CreateDefaultSubobject<USceneComponent>(TEXT("RoomRoot"));
    SetRootComponent(RoomRoot);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UMaterial> Material(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    CubeAsset = Cube.Object;
    SphereAsset = Sphere.Object;
    ShapeMaterial = Material.Object;
    static ConstructorHelpers::FObjectFinder<UTextureCube> Sky(TEXT("/Engine/MapTemplates/Sky/DaylightAmbientCubemap.DaylightAmbientCubemap"));
    if (Sky.Succeeded()) AmbientSky = Sky.Object;
}

UStaticMeshComponent* AMorphRoom::AddBlock(const FName Name, const FVector Location, const FVector Scale, const FLinearColor Color, const FRotator Rotation, const bool bCollision)
{
    UStaticMeshComponent* Mesh = NewObject<UStaticMeshComponent>(this, Name);
    Mesh->SetupAttachment(RoomRoot);
    Mesh->SetStaticMesh(CubeAsset);
    Mesh->SetRelativeLocation(Location);
    Mesh->SetRelativeRotation(Rotation);
    Mesh->SetRelativeScale3D(Scale);
    Mesh->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    Mesh->SetCollisionResponseToAllChannels(bCollision ? ECR_Block : ECR_Ignore);
    if (ShapeMaterial)
    {
        UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(ShapeMaterial, this);
        Material->SetVectorParameterValue(TEXT("Color"), Color);
        Mesh->SetMaterial(0, Material);
    }
    Mesh->RegisterComponent();
    return Mesh;
}

void AMorphRoom::AddSign(const FString Text, const FVector Location, const FRotator Rotation, const FColor Color)
{
    UTextRenderComponent* Sign = NewObject<UTextRenderComponent>(this);
    Sign->SetupAttachment(RoomRoot);
    Sign->SetRelativeLocationAndRotation(Location, Rotation);
    Sign->SetHorizontalAlignment(EHTA_Center);
    Sign->SetWorldSize(14.0f);
    Sign->SetTextRenderColor(Color);
    Sign->SetText(FText::FromString(Text));
    Sign->RegisterComponent();
}

void AMorphRoom::BeginPlay()
{
    Super::BeginPlay();
    AddBlock(TEXT("Floor"), FVector(0, 0, -10), FVector(16, 14, .2), FLinearColor(.16, .19, .23));
    AddBlock(TEXT("RampVisual20Degrees"), FVector(220, -240, 64.3067f), FVector(4.2, 2.8, .16), FLinearColor(.24, .3, .34), FRotator(20, 0, 0), false);
    const FVector RampCenter(220, -240, 64.3067f);
    const FQuat RampRotation = FRotator(20, 0, 0).Quaternion();
    const auto RampPoint = [&RampCenter, &RampRotation](const FVector& Point) { return RampCenter + RampRotation.RotateVector(Point); };
    const TArray<FVector> Vertices = { RampPoint(FVector(-210, -140, 8)), RampPoint(FVector(-210, 140, 8)), RampPoint(FVector(210, 140, 8)), RampPoint(FVector(210, -140, 8)) };
    const TArray<int32> Triangles = { 0, 1, 2, 0, 2, 3 };
    UE_LOG(LogMorphRig, Log, TEXT("MR_RAMP_TOP low=%s high=%s normal=%s"), *Vertices[0].ToString(), *Vertices[3].ToString(), *RampRotation.RotateVector(FVector::UpVector).ToString());
    TArray<FVector> Normals;
    Normals.Init(RampRotation.RotateVector(FVector::UpVector), 4);
    const TArray<FVector2D> UV0 = { FVector2D(0, 0), FVector2D(0, 1), FVector2D(1, 1), FVector2D(1, 0) };
    TArray<FLinearColor> Colors;
    Colors.Init(FLinearColor::White, 4);
    TArray<FProcMeshTangent> Tangents;
    Tangents.Init(FProcMeshTangent(), 4);
    RampCollision = NewObject<UProceduralMeshComponent>(this, TEXT("Ramp20Degrees"));
    RampCollision->SetupAttachment(RoomRoot);
    RampCollision->bUseAsyncCooking = false;
    RampCollision->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, UV0, Colors, Tangents, true);
    RampCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    RampCollision->SetCollisionResponseToAllChannels(ECR_Block);
    RampCollision->GetBodySetup()->CollisionTraceFlag = CTF_UseComplexAsSimple;
    RampCollision->SetVisibility(false);
    RampCollision->RegisterComponent();
    RampCollision->RecreatePhysicsState();
    AddSign(TEXT("20 DEGREE RAMP"), FVector(210, -390, 65), FRotator(0, 0, 0), FColor::Silver);
    for (int32 Step = 0; Step < 4; ++Step)
    {
        AddBlock(FName(*FString::Printf(TEXT("Step20cm_%d"), Step)), FVector(60 + Step * 40, 260, (Step + 1) * 10), FVector(.4, 2.6, (Step + 1) * .2), FLinearColor(.27, .29, .32));
    }
    AddSign(TEXT("20 cm STEPS"), FVector(130, 390, 65), FRotator::ZeroRotator, FColor::Silver);

    AddBlock(TEXT("ContactStationTop"), FVector(-60, -330, 90), FVector(1.5, .85, .1), FLinearColor(.2, .25, .3));
    for (const float X : { -120.0f, 0.0f })
    {
        AddBlock(FName(*FString::Printf(TEXT("ContactStationLeg_%d"), static_cast<int32>(X))), FVector(X, -330, 45), FVector(.09, .7, .9), FLinearColor(.12, .14, .17));
    }
    AddBlock(TEXT("ContactPad"), FVector(-60, -330, 96), FVector(.45, .45, .025), FLinearColor(.02, .65, .75), FRotator::ZeroRotator, false);
    AddSign(TEXT("PROP CONTACT / UPLINK"), FVector(-60, -390, 120), FRotator::ZeroRotator, FColor::Cyan);

    for (int32 Index = 0; Index < 3; ++Index)
    {
        USceneComponent* Target = NewObject<USceneComponent>(this, FName(*FString::Printf(TEXT("AimTarget_%d"), Index)));
        Target->SetupAttachment(RoomRoot);
        TargetOrigins[Index] = FVector(350, -180 + Index * 180, 145);
        Target->SetRelativeLocation(TargetOrigins[Index]);
        Target->RegisterComponent();
        TargetRoots.Add(Target);
        UStaticMeshComponent* Visual = NewObject<UStaticMeshComponent>(this);
        Visual->SetupAttachment(Target);
        Visual->SetStaticMesh(SphereAsset);
        Visual->SetRelativeScale3D(FVector(.3f));
        Visual->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        Visual->SetCollisionResponseToAllChannels(ECR_Ignore);
        Visual->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
        Visual->SetRelativeLocation(FVector::ZeroVector);
        if (ShapeMaterial)
        {
            UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(ShapeMaterial, this);
            Material->SetVectorParameterValue(TEXT("Color"), Index == 1 ? FLinearColor(.95f, .4f, .04f) : FLinearColor(.03f, .7f, .85f));
            Visual->SetMaterial(0, Material);
        }
        Visual->RegisterComponent();
        Visual->ComponentTags.Add(TEXT("MorphTarget"));
        TargetVisuals.Add(Visual);
        AddBlock(FName(*FString::Printf(TEXT("TargetPost_%d"), Index)), TargetOrigins[Index] - FVector(0, 0, 75), FVector(.07, .07, 1.3), FLinearColor(.12, .14, .17));
    }
    AddSign(TEXT("MOVING AIM TARGETS"), FVector(350, 0, 205), FRotator::ZeroRotator, FColor::White);

    UDirectionalLightComponent* Key = NewObject<UDirectionalLightComponent>(this, TEXT("KeyLight"));
    Key->SetupAttachment(RoomRoot);
    Key->SetWorldRotation(FRotator(-48, 140, 0));
    Key->SetIntensity(5.0f);
    Key->SetLightColor(FColor(255, 239, 218));
    Key->SetMobility(EComponentMobility::Movable);
    Key->RegisterComponent();

    USkyLightComponent* Fill = NewObject<USkyLightComponent>(this, TEXT("AmbientFill"));
    Fill->SetupAttachment(RoomRoot);
    if (AmbientSky)
    {
        Fill->SourceType = SLS_SpecifiedCubemap;
        Fill->Cubemap = AmbientSky;
    }
    Fill->SetIntensity(.6f);
    Fill->SetLightColor(FColor(220, 230, 245));
    Fill->bLowerHemisphereIsBlack = false;
    Fill->SetMobility(EComponentMobility::Movable);
    Fill->RegisterComponent();

    for (int32 Index = 0; Index < 3; ++Index)
    {
        UPointLightComponent* Light = NewObject<UPointLightComponent>(this);
        Light->SetupAttachment(RoomRoot);
        Light->SetRelativeLocation(FVector(-260 + Index * 280, Index % 2 ? 260 : -260, 260));
        Light->SetIntensity(400.0f);
        Light->SetAttenuationRadius(650.0f);
        Light->SetLightColor(FColor(235, 240, 248));
        Light->SetMobility(EComponentMobility::Movable);
        Light->RegisterComponent();
    }
}

void AMorphRoom::Tick(const float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    Clock += DeltaSeconds;
    if (!bTargetsMoving) return;
    for (int32 Index = 0; Index < TargetRoots.Num(); ++Index)
    {
        FVector Location = TargetOrigins[Index];
        Location.X += FMath::Sin(Clock * .8f + Index * 1.7f) * 65.0f;
        Location.Z += FMath::Sin(Clock * 1.3f + Index) * 22.0f;
        TargetRoots[Index]->SetRelativeLocation(Location);
    }
}
