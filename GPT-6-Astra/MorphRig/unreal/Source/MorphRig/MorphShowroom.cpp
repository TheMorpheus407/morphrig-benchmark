#include "MorphRig.h"
#include "Modules/ModuleManager.h"
#include "Animation/AnimSequence.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Engine/SkyLight.h"
#include "Components/LightComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/TextureCube.h"
#include "Animation/MorphTarget.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundWave.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/App.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformMisc.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"
#include "UnrealClient.h"

IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl,MorphRig,"MorphRig");
DEFINE_LOG_CATEGORY_STATIC(LogMorphRig,Log,All);

AMorphGameMode::AMorphGameMode() { DefaultPawnClass=nullptr;PlayerControllerClass=AMorphController::StaticClass(); }
void AMorphGameMode::BeginPlay() { Super::BeginPlay();GetWorld()->SpawnActor<AMorphShowroom>(); }
AMorphShowroom::AMorphShowroom() {
    PrimaryActorTick.bCanEverTick=true;PrimaryActorTick.TickGroup=TG_PostUpdateWork;RootComponent=CreateDefaultSubobject<USceneComponent>("Root");
    Camera=CreateDefaultSubobject<UCameraComponent>("InspectionCamera");Camera->SetupAttachment(RootComponent);Camera->FieldOfView=45;
}
static TSharedPtr<FJsonObject> ReadJSON(const FString& File) {
    FString Text;TSharedPtr<FJsonObject> Result;
    if(FFileHelper::LoadFileToString(Text,*File))FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Result);
    return Result;
}
void AMorphShowroom::LoadData() {
    FString Path=FPaths::ProjectContentDir()/"Data";
    if(auto Root=ReadJSON(Path/"animation_manifest.json")) {
        const TArray<TSharedPtr<FJsonValue>>* Entries=nullptr;
        if(Root->TryGetArrayField(TEXT("animations"),Entries))for(auto V:*Entries) {
            auto O=V->AsObject();FMorphClip C;C.Id=O->GetStringField(TEXT("id"));C.Layer=O->GetStringField(TEXT("layer"));
            C.RootPolicy=O->GetStringField(TEXT("root_motion_policy"));C.Duration=O->GetNumberField(TEXT("duration"));C.Loop=O->GetBoolField(TEXT("loop"));
            double Speed=0;O->TryGetNumberField(TEXT("nominal_speed_cm_s"),Speed);C.NominalSpeed=Speed;
            const TArray<TSharedPtr<FJsonValue>>* Events=nullptr;
            if(O->TryGetArrayField(TEXT("events"),Events))for(auto E:*Events) {FMorphEvent Event;Event.Name=E->AsObject()->GetStringField(TEXT("name"));Event.Time=E->AsObject()->GetNumberField(TEXT("time"));C.Events.Add(Event);}
            Clips.Add(C.Id,C);ClipOrder.Add(C.Id);
            UAnimSequence* Seq=LoadObject<UAnimSequence>(nullptr,*FString::Printf(TEXT("/Game/Operative/Animations/%s.%s"),*C.Id,*C.Id));
            if(Seq)Sequences.Add(C.Id,Seq);else UE_LOG(LogMorphRig,Error,TEXT("Missing required animation %s"),*C.Id);
        }
    }
    Dialogue=LoadObject<USoundWave>(nullptr,TEXT("/Game/Operative/Dialogue.Dialogue"));
    // External face curves are editable, sampled in clip seconds, and staged with cooked data.
    if(auto F=ReadJSON(Path/"facial_animation_curves.json")) {
        const TSharedPtr<FJsonObject>* Curves=nullptr;
        if(F->TryGetObjectField(TEXT("curves"),Curves))for(const auto& Pair:(*Curves)->Values) {
            TArray<FVector2D> Keys;
            for(auto K:Pair.Value->AsArray()) {auto XY=K->AsArray();if(XY.Num()>=2)Keys.Add(FVector2D(XY[0]->AsNumber(),XY[1]->AsNumber()));}
            FaceCurves.Add(FString(Pair.Key),Keys);
        }
        const TSharedPtr<FJsonObject>* ClipFaces=nullptr;
        if(F->TryGetObjectField(TEXT("clips"),ClipFaces))for(const auto& Pair:(*ClipFaces)->Values) {
            TMap<FString,TArray<FVector2D>> CurvesForClip;
            TSet<FString> Names;
            for(auto Frame:Pair.Value->AsArray())for(const auto& Value:Frame->AsObject()->GetObjectField(TEXT("values"))->Values)Names.Add(FString(Value.Key));
            for(auto Frame:Pair.Value->AsArray()) {
                float T=Frame->AsObject()->GetNumberField(TEXT("time"));auto Values=Frame->AsObject()->GetObjectField(TEXT("values"));
                for(const FString& Name:Names) {double V=0;Values->TryGetNumberField(Name,V);CurvesForClip.FindOrAdd(Name.Replace(TEXT("."),TEXT("_"))).Add(FVector2D(T,V));}
            }
            FaceClipCurves.Add(FString(Pair.Key),CurvesForClip);
        }
    }
    FrameCSV="elapsed_s,frame_ms,instances,lod,clip,action_rate,warmed_up,resolution,rendered_lod\n";
}
void AMorphShowroom::BuildRoom() {
    auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    auto* Base=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Operative/M_Stage.M_Stage"));
    auto Box=[&](FVector Loc,FVector Scale,FRotator Rot,FLinearColor Color) {
        auto* A=GetWorld()->SpawnActor<AStaticMeshActor>(Loc,Rot);auto* C=A->GetStaticMeshComponent();C->SetMobility(EComponentMobility::Movable);
        C->SetStaticMesh(Cube);C->SetWorldScale3D(Scale);C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        if(Base) { C->SetMaterial(0,Base);auto* M=C->CreateAndSetMaterialInstanceDynamic(0);M->SetVectorParameterValue("Color",Color); }
        return C;
    };
    Box(FVector(0,0,-10),FVector(24,20,.2),FRotator::ZeroRotator,FLinearColor(.13,.16,.19));
    Box(FVector(500,0,48),FVector(3.0,2.4,.18),FRotator(20,0,0),FLinearColor(.22,.26,.29));
    Box(FVector(750,0,54),FVector(2.1,2.4,1.08),FRotator::ZeroRotator,FLinearColor(.22,.26,.29));
    for(int I=0;I<4;I++)Box(FVector(-420-I*50,150,10*(I+1)),FVector(.5,2,0.2*(I+1)),FRotator::ZeroRotator,FLinearColor(.2+I*.015,.24,.27));
    // Contact station, contrasting lane and low room perimeter.
    Box(FVector(250,-280,45),FVector(1.8,.7,.9),FRotator::ZeroRotator,FLinearColor(.19,.22,.24));
    for(int I=0;I<11;I++)Box(FVector(I*100-500,0,.3),FVector(.014,12,.005),FRotator::ZeroRotator,FLinearColor(.27,.31,.34))->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    for(int I=0;I<9;I++)Box(FVector(0,I*100-400,.4),FVector(16,.014,.005),FRotator::ZeroRotator,FLinearColor(.27,.31,.34))->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    for(int I=0;I<3;I++) {auto* T=Box(FVector(650,-350-I*150,95),FVector(.13,.65,1.2),FRotator::ZeroRotator,FLinearColor(.35,.48,.5));T->SetCollisionEnabled(ECollisionEnabled::NoCollision);T->SetCollisionResponseToAllChannels(ECR_Ignore);T->GetOwner()->SetActorEnableCollision(false);Targets.Add(T);}
    auto* Key=GetWorld()->SpawnActor<ADirectionalLight>(FVector(0,0,400),FRotator(-50,140,0));Key->GetLightComponent()->SetIntensity(3.0);Key->GetLightComponent()->SetLightColor(FLinearColor(1,.97,.93));
    auto* KeyLight=CastChecked<UDirectionalLightComponent>(Key->GetLightComponent());
    // The room is only 24 m wide. Tight cascades and short contact rays keep a
    // grounded sole attached to its shadow without a large global depth bias.
    KeyLight->SetMobility(EComponentMobility::Movable);
    KeyLight->SetDynamicShadowDistanceMovableLight(2500);
    KeyLight->SetShadowBias(.15);
    KeyLight->SetShadowSlopeBias(.15);
    KeyLight->ContactShadowLengthInWS=true;
    KeyLight->ContactShadowLength=20;
    KeyLight->MarkRenderStateDirty();
    auto* Fill=GetWorld()->SpawnActor<APointLight>(FVector(300,-200,350),FRotator::ZeroRotator);Fill->PointLightComponent->SetIntensity(24000);Fill->PointLightComponent->SetAttenuationRadius(1800);Fill->PointLightComponent->SetLightColor(FLinearColor(.78,.88,1));
    Fill->PointLightComponent->SetCastShadows(false);
    auto* Rim=GetWorld()->SpawnActor<APointLight>(FVector(-150,300,350),FRotator::ZeroRotator);Rim->PointLightComponent->SetIntensity(22000);Rim->PointLightComponent->SetAttenuationRadius(1600);Rim->PointLightComponent->SetLightColor(FLinearColor(.8,.93,1));
    Rim->PointLightComponent->SetCastShadows(false);
    auto* Sky=GetWorld()->SpawnActor<ASkyLight>();Sky->GetLightComponent()->SetIntensity(.7);Sky->GetLightComponent()->SetLightColor(FLinearColor::White);
    if(auto* Ambient=LoadObject<UTextureCube>(nullptr,TEXT("/Engine/MapTemplates/Sky/DaylightAmbientCubemap.DaylightAmbientCubemap"))) {Sky->GetLightComponent()->SourceType=SLS_SpecifiedCubemap;Sky->GetLightComponent()->SetCubemap(Ambient);}
    Sky->GetLightComponent()->RecaptureSky();
}
void AMorphShowroom::BeginPlay() {
    Super::BeginPlay();LoadData();BuildRoom();
    Hero=GetWorld()->SpawnActor<AMorphOperative>(FVector(0,0,100),FRotator::ZeroRotator);Hero->Room=this;Operatives.Add(Hero);
    if(Hero->GetMesh()->GetSkeletalMeshAsset())for(auto Morph:Hero->GetMesh()->GetSkeletalMeshAsset()->GetMorphTargets())MorphNames.Add(Morph->GetName());
    MorphNames.Sort();
    MorphNames.Append({"eye_yaw.L","eye_pitch.L","eye_yaw.R","eye_pitch.R"});
    auto* PC=Cast<AMorphController>(UGameplayStatics::GetPlayerController(this,0));
    if(PC) {PC->Room=this;PC->Possess(Hero);PC->SetViewTarget(this);PC->bShowMouseCursor=true;FInputModeGameAndUI Mode;Mode.SetHideCursorDuringCapture(false);PC->SetInputMode(Mode);}
    SetCamera(0);BuildUI();
    FParse::Value(FCommandLine::Get(),TEXT("MorphCapture="),CaptureMode);
    FParse::Value(FCommandLine::Get(),TEXT("MorphSeconds="),QuitAfter);
    FParse::Value(FCommandLine::Get(),TEXT("MorphScreenshotAt="),ScreenshotAt);
    FParse::Value(FCommandLine::Get(),TEXT("MorphCaptureDir="),CaptureDir);
    FParse::Value(FCommandLine::Get(),TEXT("MorphEvidenceDir="),EvidenceDir);
    FParse::Value(FCommandLine::Get(),TEXT("MorphCaptureFPS="),CaptureFPS);
    if(!CaptureDir.IsEmpty()) {FApp::SetUseFixedTimeStep(true);FApp::SetFixedDeltaTime(1.0/FMath::Max(1.f,CaptureFPS));}
    int32 Count=1;FParse::Value(FCommandLine::Get(),TEXT("MorphInstances="),Count);if(Count==10)ToggleCount();
    if(FParse::Param(FCommandLine::Get(),TEXT("MorphDemo")))StartDemo();
    TerrainDemo=FParse::Param(FCommandLine::Get(),TEXT("MorphTerrain"));
    if(TerrainDemo){
        Hero->ResetOperative();Hero->SetActorLocation(FVector(260,0,100));CameraMode=2;
        for(int32 I=0;I<Targets.Num();I++)Targets[I]->SetWorldLocation(FVector(450,-450-I*180,95));
    }
    if(!CaptureMode.IsEmpty()) {
        UIVisible=FParse::Param(FCommandLine::Get(),TEXT("MorphShowUI"));if(Panel)Panel->SetVisibility(UIVisible?EVisibility::Visible:EVisibility::Collapsed);
        if(CaptureMode=="face") {SetCamera(4);Hero->Request("dialogue",true);}
        if(CaptureMode=="turntable") {SetCamera(1);Hero->Request("idle_relaxed",true);}
        if(CaptureMode=="motion")StartDemo();
    }
    FString Initial;FParse::Value(FCommandLine::Get(),TEXT("MorphClip="),Initial);if(!Initial.IsEmpty())Hero->Request(Initial,true);
    Trace(FString::Printf(TEXT("loaded=%d/96 morph_controls=%d engine=%s instances=%d"),Sequences.Num(),MorphNames.Num(),*FEngineVersion::Current().ToString(),Operatives.Num()));
    if(auto* Mesh=Hero->GetMesh()->GetSkeletalMeshAsset())Trace(FString::Printf(TEXT("mesh bounds height=%.3fcm bones=%d root=%s materials=%d LODs=%d"),Mesh->GetBounds().BoxExtent.Z*2,Mesh->GetRefSkeleton().GetNum(),*Mesh->GetRefSkeleton().GetBoneName(0).ToString(),Mesh->GetMaterials().Num(),Mesh->GetLODNum()));
    for(auto Morph:Hero->GetMesh()->GetSkeletalMeshAsset()->GetMorphTargets())Trace(FString::Printf(TEXT("morph %s LOD0_deltas=%d LOD1_deltas=%d LOD2_deltas=%d"),*Morph->GetName(),Morph->GetNumDeltasForLOD(0),Morph->GetNumDeltasForLOD(1),Morph->GetNumDeltasForLOD(2)));
    if(auto* Data=Hero->GetMesh()->GetSkeletalMeshAsset()->GetResourceForRendering())for(int32 I=0;I<Data->LODRenderData.Num();I++)Trace(FString::Printf(TEXT("render LOD%d triangles=%d vertices=%d sections=%d"),I,Data->LODRenderData[I].GetTotalFaces(),Data->LODRenderData[I].GetNumVertices(),Data->LODRenderData[I].RenderSections.Num()));
}
void AMorphShowroom::Trace(const FString& Text) {
    LastTrace=Text;FString Line=FString::Printf(TEXT("%.4f %s\n"),Elapsed,*Text);TraceText+=Line;UE_LOG(LogMorphRig,Log,TEXT("%s"),*Line);
}
void AMorphShowroom::SetCamera(int32 Mode) { CameraMode=Mode; }
void AMorphShowroom::SetLOD(int32 L) { LOD=L;for(auto* A:Operatives)A->GetMesh()->SetForcedLOD(L);Trace(FString::Printf(TEXT("LOD=%d (0 auto, 1 LOD0, 2 LOD1, 3 LOD2)"),LOD)); }
void AMorphShowroom::ToggleCount() {
    if(Operatives.Num()>1) {for(int32 I=1;I<Operatives.Num();I++)Operatives[I]->Destroy();Operatives.SetNum(1);}
    else for(int32 I=1;I<10;I++) {
        auto* A=GetWorld()->SpawnActor<AMorphOperative>(FVector((I/4)*170,(I%4)*180+150,100),FRotator::ZeroRotator);A->Room=this;A->InstanceNumber=I;A->BaseTime=I*.13;A->SetTeam(I%2==1);A->GetMesh()->SetForcedLOD(LOD);Operatives.Add(A);
    }
    Trace(FString::Printf(TEXT("instances=%d"),Operatives.Num()));
}
void AMorphShowroom::SelectClip(const FString& Id) { Hero->Request(Id,true); }
void AMorphShowroom::SetDisable(const FString& State) {
    if(Hero->IsTerminal())return;
    FString Previous=Hero->Disable;
    // Exit sustained casts before applying silence, so the authored cancel can enter.
    if(State=="silence" && (Hero->ActionId.StartsWith("channel_") || Hero->ActionId.StartsWith("charge_")))Hero->StopAction(true);
    bool Suppress=(State=="silence" && Hero->ActionId.StartsWith("cast_")) || (State=="disarm" && (Hero->ActionId.StartsWith("ranged_") || Hero->ActionId.StartsWith("melee_")));
    if(Suppress) {Hero->PreviousActionId=Hero->ActionId;Hero->PreviousActionTime=Hero->ActionTime;Hero->ActionId.Empty();Hero->ActionBlend=0;Hero->ActionGeneration++;Hero->FiredEvents.Empty();Trace("suppressed remaining action markers");}
    Hero->Disable=State;Hero->Stasis=State=="stasis";
    if(State=="root" || State=="stasis") {Hero->GetCharacterMovement()->StopMovementImmediately();Hero->GetCharacterMovement()->DisableMovement();}
    else if(Previous=="root" || Previous=="stasis")Hero->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    if(State=="stun")Hero->Request("stun_start");
    else if(State=="sleep")Hero->Request("sleep_start");
    else if(State=="fear")SetFacePreset("concern");
    else if(State=="charm")SetFacePreset("joy");
    else if(State=="taunt")SetFacePreset("anger");
    Trace("disable="+State);
}
void AMorphShowroom::SetFacePreset(const FString& Preset) {
    Hero->FaceControls.Empty();Hero->FacePreset=Preset;
    // Names match the authoritative rig contract and imported morph controls.
    auto Set=[&](FString Key,float V) {Key=Key.Replace(TEXT("."),TEXT("_"));ensureMsgf(MorphNames.Contains(Key),TEXT("Missing facial preset control: %s"),*Key);Hero->FaceControls.Add(Key,V);};
    if(Preset=="joy") {Set("smile.L",.8);Set("smile.R",.8);Set("cheek.L",.5);Set("cheek.R",.5);}
    if(Preset=="anger") {Set("brow_down.L",.8);Set("brow_down.R",.8);Set("squint.L",.55);Set("squint.R",.55);}
    if(Preset=="concern") {Set("brow_up.L",.65);Set("frown.L",.65);Set("frown.R",.65);}
    if(Preset=="surprise") {Set("brow_up.L",.95);Set("brow_up.R",.95);Set("jaw_open",.4);Set("funnel",.4);}
    if(Preset=="pain") {Set("blink.L",.6);Set("squint.R",.8);Set("brow_down.L",.65);Set("frown.R",.65);}
    if(Preset=="focus") {Set("squint.L",.4);Set("squint.R",.35);Set("brow_down.L",.3);Set("lip_close",.45);}
}
void AMorphShowroom::ApplyMaterialMode() {
    auto* Normal=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Operative/M_Normals.M_Normals"));
    for(auto* A:Operatives)for(int32 I=0;I<A->GetMesh()->GetNumMaterials();I++) {
        if(ShowNormals && Normal)A->GetMesh()->SetMaterial(I,Normal);
        else if(A->GetMesh()->GetSkeletalMeshAsset())A->GetMesh()->SetMaterial(I,A->GetMesh()->GetSkeletalMeshAsset()->GetMaterials()[I].MaterialInterface);
    }
    if(!ShowNormals)for(auto* A:Operatives)A->SetTeam(A->TeamB);
}
void AMorphShowroom::StartDemo() {Demo=true;DemoStep=-1;DemoClock=0;Hero->ResetOperative();Trace("deterministic sequence start");}
void AMorphShowroom::TakeScreenshot(const FString& Name) {
    FString Dir=CaptureDir.IsEmpty()?FPaths::ProjectSavedDir()/"Screenshots":CaptureDir;IFileManager::Get().MakeDirectory(*Dir,true);
    FScreenshotRequest::RequestScreenshot(Dir/Name,UIVisible,false);
}
void AMorphShowroom::SaveLogs() {
    FString Dir=EvidenceDir.IsEmpty()?FPaths::ProjectSavedDir()/"Evidence":EvidenceDir;IFileManager::Get().MakeDirectory(*Dir,true);
    FString Suffix=FString::Printf(TEXT("%d_actors"),Operatives.Num());
    FFileHelper::SaveStringToFile(FrameCSV,*(Dir/("frames_"+Suffix+".csv")));
    FFileHelper::SaveStringToFile(TraceText,*(Dir/"state_event_trace.log"));
}
void AMorphShowroom::EndPlay(const EEndPlayReason::Type Reason) {SaveLogs();Super::EndPlay(Reason);}
FString AMorphShowroom::Status() const {
    if(!Hero)return "Loading character";
    FString Id=Hero->ActionId.IsEmpty()?Hero->BaseId:Hero->ActionId;float T=Hero->ActionId.IsEmpty()?Hero->BaseTime:Hero->ActionTime;
    float Length=Clips.Contains(Id)?Clips[Id].Duration:0;
    return FString::Printf(TEXT("%s   %.2f / %.2fs\n%.2fx   %.0f cm/s   %d Operative%s   LOD %s\nAim yaw %+05.1f  pitch %+05.1f   %s\nEvent: %s\n%.1f ms / %.0f FPS"),*Id,T,Length,Hero->ActionRate,Hero->GetVelocity().Size2D(),Operatives.Num(),Operatives.Num()>1?TEXT("s"):TEXT(""),LOD==0?*FString::Printf(TEXT("auto/%d"),Hero->GetMesh()->GetPredictedLODLevel()):*FString::FromInt(LOD-1),Hero->AimYaw,Hero->AimPitch,*Hero->Disable,*Hero->LastEvent,FApp::GetDeltaTime()*1000,1/FMath::Max(.0001,FApp::GetDeltaTime()));
}
void AMorphShowroom::Tick(float Dt) {
    Super::Tick(Dt);if(!Hero)return;Elapsed+=Dt;
    int32 Width=0,Height=0;if(auto* PC=UGameplayStatics::GetPlayerController(this,0))PC->GetViewportSize(Width,Height);
    FrameCSV+=FString::Printf(TEXT("%.6f,%.5f,%d,%d,%s,%.2f,%d,%dx%d,%d\n"),Elapsed,FApp::GetDeltaTime()*1000,Operatives.Num(),LOD,Hero->ActionId.IsEmpty()?*Hero->BaseId:*Hero->ActionId,Hero->ActionRate,Elapsed>=10?1:0,Width,Height,Hero->GetMesh()->GetPredictedLODLevel());
    if(MovableTargets)for(int32 I=0;I<Targets.Num();I++)Targets[I]->SetWorldLocation(FVector(650,-500+FMath::Sin(Elapsed*.8+I)*150,95+FMath::Sin(Elapsed+I)*25));
    FVector Focus=Hero->GetActorLocation()-FVector(0,0,5),Offset;
    if(CameraMode==0) {Offset=FVector(391,-333.5,172.5);Focus.Z-=10;}
    else if(CameraMode==1)Offset=FVector(420,0,35);
    else if(CameraMode==2)Offset=FVector(0,-420,35);
    else if(CameraMode==3) {Offset=FVector(1050,0,1550);Focus.Z=40;}
    else {Focus=Hero->GetMesh()->GetSocketLocation("head")+FVector(0,0,5);Offset=FVector(95,-10,4);}
    if(TerrainDemo) {Focus.Z-=15;Offset=FVector(130,520,370);}
    if(Operatives.Num()>1 && CameraMode!=4) {Focus=FVector::ZeroVector;for(auto* A:Operatives)Focus+=A->GetActorLocation();Focus/=Operatives.Num();Offset=FVector(977.5,-1035,920);}
    if(CaptureMode=="turntable") {float A=Elapsed*2*PI/12;Offset=FVector(FMath::Cos(A)*410,FMath::Sin(A)*410,40);}
    Camera->SetWorldLocation(Focus+Offset);Camera->SetWorldRotation((-Offset).Rotation());Camera->FieldOfView=CameraMode==4?32:45;
    if(Demo) {
        DemoClock+=Dt;
        struct Entry{float At;const char* Action;};
        static const Entry Sequence[]={{0,"idle_combat"},{2,"move"},{4,"ranged_burst"},{5,"hit_l"},{6,"cast_directional"},{8,"channel_start"},{10,"interrupt"},{11,"charge_start"},{12.5,"finish"},{14,"uplink_start"},{16,"interrupt"},{17,"reload"},{20,"deploy"},{22,"dash_f"},{23,"jump_start"},{23.8,"death_front"},{27,"respawn"},{30,"knockdown_back"},{33,"finish"},{36,"blink_out"},{38,"slow"},{39,"melee_1"},{41,"fast"},{42,"melee_2"},{44,"normal"},{45,"stun_start"},{47,"finish"},{49,"done"}};
        if(DemoStep+1<int32(UE_ARRAY_COUNT(Sequence)) && DemoClock>=Sequence[DemoStep+1].At) {
            DemoStep++;FString A=Sequence[DemoStep].Action;
            if(A=="move") {Hero->BrowserMode=false;Hero->ActionId.Empty();Hero->AimWeight=.55;}
            else if(A=="interrupt")Hero->StopAction(true);
            else if(A=="finish")Hero->StopAction(false);
            else if(A=="slow")Hero->ActionRate=.5;
            else if(A=="fast")Hero->ActionRate=1.5;
            else if(A=="normal")Hero->ActionRate=1;
            else if(A=="done") {Demo=false;Trace("deterministic sequence complete");SaveLogs();}
            else Hero->Request(A);
        }
        if(DemoClock>=2 && DemoClock<7.5) {Hero->GetCharacterMovement()->MaxWalkSpeed=150;Hero->AddMovementInput(FVector(0,1,0));Hero->Facing=0;Hero->AimYaw=FMath::Sin(DemoClock)*35;Hero->AimPitch=10;}
    }
    if(TerrainDemo) {
        Hero->GetCharacterMovement()->MaxWalkSpeed=150;
        if(Elapsed<3.1)Hero->AddMovementInput(FVector(1,0,0));
        if(Elapsed>=4 && TerrainStage<1) {TerrainStage=1;Hero->SetActorLocation(FVector(-360,150,100));Hero->ActionId.Empty();Trace("terrain: begin 20cm stairs");}
        if(Elapsed>=4 && Elapsed<5.55)Hero->AddMovementInput(FVector(-1,0,0));
        static float NextTerrainTrace=0;
        if(Elapsed>=NextTerrainTrace) {NextTerrainTrace+=.1;Trace(FString::Printf(TEXT("terrain pos=%s feetL=%.2f feetR=%.2f pelvis=%.2f ankleL=%s ankleR=%s groundL=%.3f groundR=%.3f falling=%d"),*Hero->GetActorLocation().ToCompactString(),Hero->FootOffsetL,Hero->FootOffsetR,Hero->PelvisCorrection,*Hero->GetMesh()->GetSocketLocation("foot_L").ToCompactString(),*Hero->GetMesh()->GetSocketLocation("foot_R").ToCompactString(),Hero->GroundHeightL,Hero->GroundHeightR,int(Hero->GetCharacterMovement()->IsFalling())));}
    }
    if(ScreenshotAt>=0 && Elapsed>=ScreenshotAt) {TakeScreenshot("inspection.png");ScreenshotAt=-1;}
    if(!CaptureDir.IsEmpty() && Elapsed>=NextFrameCapture) {
        static int32 CaptureIndex=0;TakeScreenshot(FString::Printf(TEXT("frame_%06d.png"),CaptureIndex++));NextFrameCapture+=1.f/FMath::Max(1.f,CaptureFPS);
    }
    if(QuitAfter>0 && Elapsed>=QuitAfter) {SaveLogs();FPlatformMisc::RequestExit(false);QuitAfter=0;}
}
