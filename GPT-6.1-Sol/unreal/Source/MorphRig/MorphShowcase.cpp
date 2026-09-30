#include "MorphShowcase.h"
#include "MorphOperative.h"
#include "MorphAnimInstance.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PointLight.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInterface.h"
#include "Kismet/GameplayStatics.h"
#include "InputKeyEventArgs.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMemory.h"
#include "HAL/PlatformMisc.h"
#include "Serialization/JsonSerializer.h"
#include "UnrealClient.h"
#include "RenderTimer.h"
#include "DynamicRHI.h"
#include "RHI.h"

namespace
{
    const TCHAR* FaceNames[]={TEXT("blink_L"),TEXT("blink_R"),TEXT("squint_L"),TEXT("squint_R"),TEXT("brow_raise_L"),TEXT("brow_raise_R"),TEXT("brow_lower_L"),TEXT("brow_lower_R"),TEXT("cheek_L"),TEXT("cheek_R"),TEXT("jaw"),TEXT("lip_close"),TEXT("smile_L"),TEXT("smile_R"),TEXT("frown_L"),TEXT("frown_R"),TEXT("width"),TEXT("pucker"),TEXT("funnel"),TEXT("tongue"),TEXT("eye_yaw_L"),TEXT("eye_yaw_R"),TEXT("eye_pitch_L"),TEXT("eye_pitch_R"),TEXT("viseme_closure"),TEXT("viseme_labiodental"),TEXT("viseme_open"),TEXT("viseme_wide"),TEXT("viseme_round"),TEXT("viseme_tongue"),TEXT("viseme_consonant")};
    AStaticMeshActor* Box(UWorld* World,FVector Position,FVector Scale,FRotator Rotation=FRotator::ZeroRotator,const TCHAR* Asset=TEXT("/Engine/BasicShapes/Cube.Cube"))
    {
        AStaticMeshActor* Actor=World->SpawnActor<AStaticMeshActor>(Position,Rotation);
        Actor->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        Actor->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,Asset));
        Actor->SetActorScale3D(Scale);
        if(UMaterialInterface* Material=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Showcase/M_Room.M_Room")))Actor->GetStaticMeshComponent()->SetMaterial(0,Material);
        return Actor;
    }
    bool Shift(APlayerController* C){return C->IsInputKeyDown(EKeys::LeftShift)||C->IsInputKeyDown(EKeys::RightShift);}
    bool Control(APlayerController* C){return C->IsInputKeyDown(EKeys::LeftControl)||C->IsInputKeyDown(EKeys::RightControl);}
}

AMorphShowcaseMode::AMorphShowcaseMode()
{
    DefaultPawnClass=AMorphOperative::StaticClass();
    PlayerControllerClass=AMorphShowcaseController::StaticClass();
    HUDClass=AMorphShowcaseHUD::StaticClass();
}

void AMorphShowcaseMode::BeginPlay()
{
    Super::BeginPlay();
    Box(GetWorld(),FVector(0,0,-5),FVector(28,24,.1));
    Box(GetWorld(),FVector(600,-350,77),FVector(4,3,.15),FRotator(20,0,0));
    Box(GetWorld(),FVector(930,-350,148),FVector(2.8,3,.16));
    for(int32 I=0;I<5;++I)Box(GetWorld(),FVector(300+I*80,450,10*(I+1)),FVector(.8,2,.2*(I+1)));
    Box(GetWorld(),FVector(-450,350,43),FVector(2.2,1.2,.12));
    Box(GetWorld(),FVector(-530,350,20),FVector(.14,.7,.4));
    Box(GetWorld(),FVector(-370,350,20),FVector(.14,.7,.4));
    ADirectionalLight* Key=GetWorld()->SpawnActor<ADirectionalLight>(FVector(0,0,600),FRotator(-35,150,0));
    Key->GetLightComponent()->SetMobility(EComponentMobility::Movable);Key->GetLightComponent()->SetIntensity(2.2f);Key->GetLightComponent()->SetLightColor(FLinearColor(1,.96f,.92f));
    ADirectionalLight* Fill=GetWorld()->SpawnActor<ADirectionalLight>(FVector(0,0,600),FRotator(-25,220,0));
    Fill->GetLightComponent()->SetMobility(EComponentMobility::Movable);Fill->GetLightComponent()->SetIntensity(1.6f);Fill->GetLightComponent()->SetCastShadows(false);
    ADirectionalLight* Rim=GetWorld()->SpawnActor<ADirectionalLight>(FVector(0,0,600),FRotator(-30,30,0));
    Rim->GetLightComponent()->SetMobility(EComponentMobility::Movable);Rim->GetLightComponent()->SetIntensity(.8f);Rim->GetLightComponent()->SetCastShadows(false);
    for(FVector Location:{FVector(300,-300,400),FVector(-300,400,350)})
    {APointLight* Light=GetWorld()->SpawnActor<APointLight>(Location,FRotator::ZeroRotator);Light->PointLightComponent->SetMobility(EComponentMobility::Movable);Light->PointLightComponent->SetIntensity(9000);Light->PointLightComponent->SetAttenuationRadius(1800);Light->PointLightComponent->SetCastShadows(false);}
    for(FVector Location:{FVector(300,-160,190),FVector(300,160,210)})
    {
        APointLight* Light=GetWorld()->SpawnActor<APointLight>(Location,FRotator::ZeroRotator);Light->PointLightComponent->SetMobility(EComponentMobility::Movable);
        Light->PointLightComponent->SetIntensity(28000);Light->PointLightComponent->SetSourceRadius(100);Light->PointLightComponent->SetAttenuationRadius(2500);Light->PointLightComponent->SetCastShadows(false);
    }
}

void AMorphShowcaseController::BeginPlay()
{
    Super::BeginPlay();
    Operative=Cast<AMorphOperative>(GetPawn());
    if(Operative){Operative->SetActorLocation(FVector(0,0,90));Operative->SetActorRotation(FRotator::ZeroRotator);}
    ShowCamera=GetWorld()->SpawnActor<ACameraActor>();ShowCamera->GetCameraComponent()->SetFieldOfView(42);SetViewTarget(ShowCamera);
    bShowMouseCursor=true;bEnableClickEvents=true;bEnableMouseOverEvents=true;
    FInputModeGameAndUI Mode;Mode.SetHideCursorDuringCapture(false);SetInputMode(Mode);
    Targets.Add(Box(GetWorld(),FVector(450,-180,105),FVector(.35),FRotator::ZeroRotator,TEXT("/Engine/BasicShapes/Sphere.Sphere")));
    Targets.Add(Box(GetWorld(),FVector(580,260,80),FVector(.32),FRotator::ZeroRotator,TEXT("/Engine/BasicShapes/Sphere.Sphere")));
    for(AStaticMeshActor* Target:Targets)Target->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    FParse::Value(FCommandLine::Get(),TEXT("MorphView="),ViewMode);
    SetView(ViewMode);
    FParse::Value(FCommandLine::Get(),TEXT("MorphExitSeconds="),ExitSeconds);
    FParse::Value(FCommandLine::Get(),TEXT("MorphScreenshotAt="),ScreenshotAt);
    FParse::Value(FCommandLine::Get(),TEXT("MorphStartDelay="),StartDelay);bWaitingToStart=true;
    bNoHUD=FParse::Param(FCommandLine::Get(),TEXT("MorphNoHUD"));
    bPendingTurntable=FParse::Param(FCommandLine::Get(),TEXT("MorphTurntable"));
    bSweep=FParse::Param(FCommandLine::Get(),TEXT("MorphInventorySweep"));
    FString Initial;
    if(FParse::Value(FCommandLine::Get(),TEXT("MorphClip="),Initial))PendingClip=FName(*Initial);
    if(FParse::Value(FCommandLine::Get(),TEXT("MorphAction="),Initial))PendingAction=FName(*Initial);
    bPendingSequence=FParse::Param(FCommandLine::Get(),TEXT("MorphSequence"));
}

void AMorphShowcaseController::ApplyStartupOptions()
{
    FString Initial;
    bStartupApplied=true;
    if(Operative)FParse::Value(FCommandLine::Get(),TEXT("MorphRate="),Operative->Rate);
    if(Operative)
    {
        int32 LOD=0,Team=0,Expression=-1,Material=0;
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphLOD="),LOD))Operative->SetLOD(LOD);
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphTeam="),Team))Operative->SetTeam(Team);
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphExpression="),Expression))Operative->SetExpression(Expression);
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphMaterial="),Material))Operative->SetMaterialMode(Material);
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphFace="),Initial))
        {float Value=1;FParse::Value(FCommandLine::Get(),TEXT("MorphFaceValue="),Value);Operative->SetFace(FName(*Initial),Value);}
        float Yaw=0,Pitch=0;
        if(FParse::Value(FCommandLine::Get(),TEXT("MorphAimYaw="),Yaw)||FParse::Value(FCommandLine::Get(),TEXT("MorphAimPitch="),Pitch))
        {FParse::Value(FCommandLine::Get(),TEXT("MorphAimPitch="),Pitch);Operative->SetAim(Yaw,Pitch);}
    }
    if(FParse::Param(FCommandLine::Get(),TEXT("MorphPerf10")))ToggleInstances();
    if(FParse::Param(FCommandLine::Get(),TEXT("MorphPerf")))StartPerfCapture();
    bTerrain=FParse::Param(FCommandLine::Get(),TEXT("MorphTerrainTest"));
    if(bTerrain)
    {
        Operative->ResetOperative();Operative->SetActorLocation(FVector(280,-350,90));SetView(2);Operative->SetLOD(1);LoadBootSurface();
        TerrainCSV=TEXT("t,phase,actor_x,actor_y,actor_z,speed,pelvis_offset,left_ankle_z,left_ground_z,left_ik_weight,right_ankle_z,right_ground_z,right_ik_weight,left_sole_normal_error_deg,right_sole_normal_error_deg,left_foot_x,left_foot_y,left_foot_z,right_foot_x,right_foot_y,right_foot_z,left_boot_clearance_min_cm,right_boot_clearance_min_cm,left_boot_inside_step_vertices,right_boot_inside_step_vertices,left_boot_step_penetration_max_cm,right_boot_step_penetration_max_cm,left_stance_weight,right_stance_weight,body_id,body_t,base_id,gait_phase\n");
        Operative->GetMesh()->RegisterOnBoneTransformsFinalizedDelegate(FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this,&AMorphShowcaseController::RecordTerrainSample));
        Operative->Trace(TEXT("terrain_begin ramp=20deg steps=20cm"));
    }
}

void AMorphShowcaseController::SetView(int32 Mode){ViewMode=Mode%5;bFacePanel=ViewMode==3;if(bFacePanel&&Operative&&!Operative->TracePath.IsEmpty())Operative->SetLOD(1);}

void AMorphShowcaseController::PlayerTick(float Delta)
{
    Super::PlayerTick(Delta);if(!Operative||!ShowCamera)return;
    if(!bStartupApplied)
    {
        if(Operative->TracePath.IsEmpty())return;
        ApplyStartupOptions();
    }
    Elapsed+=Delta;
    if(bFacePanel&&Operative->ForcedLOD!=1)Operative->SetLOD(1);
    if(bWaitingToStart&&Elapsed>=StartDelay)
    {
        bWaitingToStart=false;Operative->Trace(TEXT("presentation_start"));
        if(!PendingClip.IsNone())Operative->Request(PendingClip,true);
        if(!PendingAction.IsNone())Operative->Request(PendingAction);
        if(bPendingSequence)StartSequence();bTurntable=bPendingTurntable;
    }
    if(bTerrain)
    {
        TerrainTime+=Delta;TerrainSampleTime+=Delta;
        if(TerrainTime>=7&&!bTerrainSteps)
        {
            bTerrainSteps=true;TerrainSampleTime=0;Operative->ResetOperative();Operative->SetActorLocation(FVector(180,450,90));
            Operative->Trace(TEXT("terrain_steps_begin"));
        }
        const float RampEnd=FParse::Param(FCommandLine::Get(),TEXT("MorphRampStop"))?650.f:970.f;
        const bool Moving=Operative->GetActorLocation().X<(bTerrainSteps?615:RampEnd);
        Operative->SetMoveInput(FVector2D(Moving?1:0,0),0);
        if(TerrainTime>=12)
        {
            bTerrain=false;Operative->SetMoveInput(FVector2D::ZeroVector,0);
            const FString File=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Verification/terrain_contacts.csv"));FFileHelper::SaveStringToFile(TerrainCSV,*File);
            Operative->Trace(TEXT("terrain_complete"));if(FParse::Param(FCommandLine::Get(),TEXT("MorphAutoExit")))ConsoleCommand(TEXT("quit"));
        }
    }
    if(!bSequence && !bSweep && !bTerrain)
    {
        const float Forward=(IsInputKeyDown(EKeys::W)?1:0)-(IsInputKeyDown(EKeys::S)?1:0);
        const float Right=(IsInputKeyDown(EKeys::D)?1:0)-(IsInputKeyDown(EKeys::A)?1:0);
        Operative->SetMoveInput(bBrowser||bFacePanel?FVector2D::ZeroVector:FVector2D(Forward,Right),Control(this)?2:Shift(this)?1:0);
    }
    if(!bBrowser)
    {
        const float Yaw=(IsInputKeyDown(EKeys::Right)?1:0)-(IsInputKeyDown(EKeys::Left)?1:0);
        const float Pitch=(IsInputKeyDown(EKeys::Up)?1:0)-(IsInputKeyDown(EKeys::Down)?1:0);
        if(Yaw!=0||Pitch!=0)Operative->SetAim(Operative->AimYaw+Yaw*Delta*50,Operative->AimPitch+Pitch*Delta*40);
    }
    if(Targets.Num())Operative->AttentionTarget=Targets[0]->GetActorLocation();
    if((bTargetAim||!Operative->AttentionState.IsNone()) && Targets.Num())
    {
        const FRotator Aim=(Targets[0]->GetActorLocation()-Operative->GetMesh()->GetSocketLocation(TEXT("chest"))).Rotation();
        Operative->SetAim(-FMath::FindDeltaAngleDegrees(Operative->GetActorRotation().Yaw,Aim.Yaw),Aim.Pitch);
    }
    if(bSequence)StepSequence(Delta);
    if(bSweep)
    {
        SweepTime-=Delta;
        if(SweepTime<=0)
        {
            SweepIndex++;
            if(SweepIndex<Operative->Inventory.Num())
            {
                Operative->ResetOperative();const FName Id=Operative->Inventory[SweepIndex];Operative->Request(Id,true);
                const FMorphClip* C=Operative->Clip(Id);SweepTime=C?C->bPose?.4f:C->Duration*(C->bLoop?2.f:1.f)+.2f:1.f;
                Operative->Trace(FString::Printf(TEXT("inventory %d/%d %s"),SweepIndex+1,Operative->Inventory.Num(),*Id.ToString()));
            }
            else {bSweep=false;Operative->Trace(TEXT("inventory_complete"));if(FParse::Param(FCommandLine::Get(),TEXT("MorphAutoExit")))ConsoleCommand(TEXT("quit"));}
        }
    }
    const FVector Origin=Operative->GetActorLocation()-FVector(0,0,88);
    const FQuat Facing=Operative->GetActorQuat();
    FVector Target=Origin+FVector(0,0,95),Offset;
    if(bTurntable)Orbit+=Delta*24;
    switch(ViewMode)
    {
        case 1:Offset=FVector(440,0,115);break;
        case 2:Offset=FVector(0,-440,115);break;
        case 3:Target=Operative->GetMesh()->GetSocketLocation(TEXT("head"))+Facing.RotateVector(FVector(0,0,10));Offset=FVector(125,-3,6);break;
        case 4:Offset=FVector(-120,-760,1120)*1.35f;break;
        default:Offset=FVector(360,-300,200);break;
    }
    if(ViewMode!=3)Offset*=CameraDistance/480.f;
    if(Crowd.Num()&&ViewMode!=3)
    {
        Target=FVector(-350,-70,95);
        Offset=(ViewMode==4?FVector(-400,-1050,1600):FVector(1100,-550,600))*(CameraDistance/550.f);
    }
    Offset=FRotator(0,Orbit,0).RotateVector(Facing.RotateVector(Offset));
    const FVector Location=Target+Offset;
    ShowCamera->SetActorLocation(Location);ShowCamera->SetActorRotation((Target-Location).Rotation());
    if(ScreenshotAt>=0 && Elapsed>=ScreenshotAt)
    {
        FString File=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Verification/showcase.png"));
        FParse::Value(FCommandLine::Get(),TEXT("MorphScreenshot="),File);
        FScreenshotRequest::RequestScreenshot(File,false,false);ScreenshotAt=-1;
    }
    if(bPerf)
    {
        PerfTime+=Delta;
        if(PerfTime>=5)
        {FrameMs.Add(Delta*1000);GameMs.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));RenderMs.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));GPUms.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()));}
        if(PerfTime>=35)FinishPerfCapture();
    }
    if(ExitSeconds>0 && Elapsed>=ExitSeconds)ConsoleCommand(TEXT("quit"));
}

void AMorphShowcaseController::LoadBootSurface()
{
    FString Text;
    if(!FFileHelper::LoadFileToString(Text,*FPaths::Combine(FPaths::ProjectContentDir(),TEXT("Data/boot_surface_bindings.json"))))
    {Operative->Trace(TEXT("terrain_geometry_error missing imported boot bindings"));return;}
    TSharedPtr<FJsonObject> Data;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Data))return;
    const FReferenceSkeleton& Ref=Operative->GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
    TArray<FTransform> Reference;Reference.SetNum(Ref.GetNum());
    for(int32 I=0;I<Ref.GetNum();++I){const int32 Parent=Ref.GetParentIndex(I);Reference[I]=Parent>=0?Ref.GetRefBonePose()[I]*Reference[Parent]:Ref.GetRefBonePose()[I];}
    for(const TSharedPtr<FJsonValue>& Value:Data->GetArrayField(TEXT("vertices")))
    {
        const TSharedPtr<FJsonObject> Row=Value->AsObject();FMorphBootVertex Sample;
        Sample.Side=Row->GetIntegerField(TEXT("side"));Sample.Vertex=Row->GetIntegerField(TEXT("vertex"));
        const auto& P=Row->GetArrayField(TEXT("position_cm"));const FVector Position(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber());
        const auto& Bones=Row->GetArrayField(TEXT("bone_indices"));const auto& Weights=Row->GetArrayField(TEXT("weights"));
        for(int32 I=0;I<Bones.Num();++I){const int32 Bone=Bones[I]->AsNumber();Sample.Bones.Add(Bone);Sample.BoneLocalPositions.Add(Reference[Bone].InverseTransformPosition(Position));Sample.Weights.Add(Weights[I]->AsNumber());}
        BootVertices.Add(MoveTemp(Sample));
    }
    Operative->Trace(FString::Printf(TEXT("terrain_geometry_ready imported_lod0_vertices=%d"),BootVertices.Num()));
}

void AMorphShowcaseController::RecordTerrainSample()
{
    if(!bTerrain||TerrainSampleTime<.05f||!Operative)return;
    // The controller ticks before pose evaluation. Read sockets only after
    // the mesh flips its completed component-space bone buffer, so capsule,
    // foot transforms and applied proxy weights describe the same pose.
    TerrainSampleTime=0;float Ankle[2],Ground[2],SoleError[2];FVector Feet[2];
    for(int32 I=0;I<2;++I)
    {
        const FName FootName=I==0?TEXT("foot_L"):TEXT("foot_R");
        const FVector Foot=Operative->GetMesh()->GetSocketLocation(FootName);Feet[I]=Foot;FHitResult Hit;
        FCollisionQueryParams Query;Query.AddIgnoredActor(Operative);
        GetWorld()->LineTraceSingleByChannel(Hit,Foot+FVector(0,0,35),Foot-FVector(0,0,65),ECC_Visibility,Query);
        Ankle[I]=Foot.Z;Ground[I]=Hit.bBlockingHit?Hit.ImpactPoint.Z:-999;
        const FReferenceSkeleton& Ref=Operative->GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
        int32 Bone=Ref.FindBoneIndex(FootName);FTransform Reference=Ref.GetRefBonePose()[Bone];
        while((Bone=Ref.GetParentIndex(Bone))>=0)Reference=Reference*Ref.GetRefBonePose()[Bone];
        const FQuat RefWorld=Operative->GetMesh()->GetComponentQuat()*Reference.GetRotation();
        const FQuat PoseWorld=Operative->GetMesh()->GetSocketQuaternion(FootName);
        const FVector SoleNormal=(PoseWorld*RefWorld.Inverse()).RotateVector(FVector::UpVector).GetSafeNormal();
        SoleError[I]=Hit.bBlockingHit?FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(SoleNormal,Hit.ImpactNormal),-1.,1.))):-999;
    }
    const FVector P=Operative->GetActorLocation();
    const UMorphAnimInstance* Anim=Cast<UMorphAnimInstance>(Operative->GetMesh()->GetAnimInstance());
    double Clearance[2]={DBL_MAX,DBL_MAX},Penetration[2]={0,0};int32 Inside[2]={0,0};
    const auto& Current=Operative->GetMesh()->GetComponentSpaceTransforms();const FTransform MeshWorld=Operative->GetMesh()->GetComponentTransform();
    FCollisionQueryParams Query;Query.AddIgnoredActor(Operative);
    for(const FMorphBootVertex& Sample:BootVertices)
    {
        FVector Component=FVector::ZeroVector;
        for(int32 I=0;I<Sample.Bones.Num();++I)Component+=Current[Sample.Bones[I]].TransformPosition(Sample.BoneLocalPositions[I])*Sample.Weights[I];
        const FVector Point=MeshWorld.TransformPosition(Component);FHitResult Floor;
        if(GetWorld()->LineTraceSingleByChannel(Floor,Point+FVector(0,0,200),Point-FVector(0,0,200),ECC_Visibility,Query))
            Clearance[Sample.Side]=FMath::Min(Clearance[Sample.Side],Point.Z-Floor.ImpactPoint.Z);
        for(int32 Step=0;Step<5;++Step)
        {
            const double Center=300+Step*80,Top=20*(Step+1);
            if(Point.X>Center-40+.001 && Point.X<Center+40-.001 && Point.Y>350 && Point.Y<550 && Point.Z>0 && Point.Z<Top-.001)
            {Inside[Sample.Side]++;Penetration[Sample.Side]=FMath::Max(Penetration[Sample.Side],Top-Point.Z);}
        }
    }
    const FString BodyId=Operative->Body.bActive?Operative->Body.Id.ToString():TEXT("none");
    const FString BaseId=Anim?Anim->EvaluatedBaseId.ToString():TEXT("none");
    TerrainCSV+=FString::Printf(TEXT("%.4f,%s,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.4f,%.4f,%d,%d,%.4f,%.4f,%.4f,%.4f,%s,%.4f,%s,%.5f\n"),TerrainTime,bTerrainSteps?TEXT("steps"):TEXT("ramp"),P.X,P.Y,P.Z,Operative->GetVelocity().Size2D(),Anim?Anim->EvaluatedPelvisOffset:0,Ankle[0],Ground[0],Anim?Anim->EvaluatedFootWeights[0]:0,Ankle[1],Ground[1],Anim?Anim->EvaluatedFootWeights[1]:0,SoleError[0],SoleError[1],Feet[0].X,Feet[0].Y,Feet[0].Z,Feet[1].X,Feet[1].Y,Feet[1].Z,Clearance[0],Clearance[1],Inside[0],Inside[1],Penetration[0],Penetration[1],Anim?Anim->EvaluatedStanceWeights[0]:0,Anim?Anim->EvaluatedStanceWeights[1]:0,*BodyId,Operative->Body.Time,*BaseId,Anim?Anim->EvaluatedGaitPhase:0);
}

bool AMorphShowcaseController::InputKey(const FInputKeyEventArgs& Params)
{
    const bool SuperResult=Super::InputKey(Params);if(!Operative)return SuperResult;
    const FKey Key=Params.Key;
    if(Key==EKeys::MouseWheelAxis){CameraDistance=FMath::Clamp(CameraDistance-Params.AmountDepressed*35,120.f,1100.f);return true;}
    if(Params.Event==IE_Released && !bBrowser)
    {
        if(Key==EKeys::C && Operative->Body.Id.ToString().StartsWith(TEXT("channel_")))Operative->ReleaseState(false);
        if(Key==EKeys::Z && Operative->Body.Id.ToString().StartsWith(TEXT("charge_")))Operative->ReleaseState(false);
        if(Key==EKeys::U && Operative->Body.Id.ToString().StartsWith(TEXT("uplink_")))Operative->ReleaseState(false);
    }
    if(Params.Event!=IE_Pressed && !(bBrowser&&Params.Event==IE_Repeat))return SuperResult;
    if(Key==EKeys::Escape){bBrowser=bFacePanel=false;return true;}
    if(bBrowser)
    {
        if(Key==EKeys::BackSpace){if(Search.Len())Search.LeftChopInline(1);BrowserPage=0;return true;}
        if(Key==EKeys::PageDown){BrowserPage++;return true;}if(Key==EKeys::PageUp){BrowserPage=FMath::Max(0,BrowserPage-1);return true;}
        if(Key==EKeys::Enter){auto Rows=FilteredClips();if(Rows.Num())SelectClip(Rows[FMath::Min(BrowserPage*16,Rows.Num()-1)]);return true;}
        const FString Name=Key.GetFName().ToString();if(Name.Len()==1){Search+=Name.ToLower();BrowserPage=0;return true;}
        if(Key==EKeys::SpaceBar||Key==EKeys::Underscore||Key==EKeys::Subtract){Search+=TEXT("_");BrowserPage=0;return true;}
        return true;
    }
    if(Key==EKeys::B){bBrowser=!bBrowser;bFacePanel=false;Search.Empty();BrowserPage=0;}
    else if(Key==EKeys::F1)SetView(0);else if(Key==EKeys::F2)SetView(1);else if(Key==EKeys::F3)SetView(2);else if(Key==EKeys::F4)SetView(3);else if(Key==EKeys::F5)SetView(4);
    else if(Key==EKeys::F8){bHelp=!bHelp;}
    else if(Key==EKeys::F9)StartSequence();else if(Key==EKeys::F10)ToggleInstances();else if(Key==EKeys::F11)StartPerfCapture();
    else if(Key==EKeys::SpaceBar)Operative->Request(TEXT("jump_start"));
    else if(Key==EKeys::X)
    {
        const FVector2D V=Operative->MoveInput;const TCHAR* Id=FMath::Abs(V.Y)>FMath::Abs(V.X)?V.Y>0?TEXT("dash_r"):TEXT("dash_l"):V.X<0?TEXT("dash_b"):TEXT("dash_f");Operative->Request(Id);
    }
    else if(Key==EKeys::V)Operative->Request(TEXT("blink_out"));
    else if(Key==EKeys::LeftMouseButton){float MX,MY;if(GetMousePosition(MX,MY) && GetHUD() && GetHUD()->GetHitBoxAtCoordinates(FVector2D(MX,MY)))return true;Operative->Request(TEXT("ranged_fire"));}
    else if(Key==EKeys::F)Operative->Request(TEXT("ranged_burst"));
    else if(Key==EKeys::One)Operative->Request(TEXT("melee_1"));else if(Key==EKeys::Two)Operative->Request(TEXT("melee_2"));else if(Key==EKeys::Three)Operative->Request(TEXT("melee_3"));
    else if(Key==EKeys::R)Operative->Request(TEXT("reload"));
    else if(Key==EKeys::G)Operative->Request(TEXT("cast_directional"));else if(Key==EKeys::J)Operative->Request(TEXT("cast_ground"));else if(Key==EKeys::K)Operative->Request(TEXT("cast_self"));
    else if(Key==EKeys::C)Operative->Request(TEXT("channel_start"));else if(Key==EKeys::Z)Operative->Request(TEXT("charge_start"));else if(Key==EKeys::U)Operative->Request(TEXT("uplink_start"));
    else if(Key==EKeys::I)Operative->ReleaseState(true);else if(Key==EKeys::P)Operative->Request(TEXT("deploy"));
    else if(Key==EKeys::H){const FVector2D V=Operative->MoveInput;Operative->Request(FMath::Abs(V.Y)>FMath::Abs(V.X)?V.Y>0?FName(TEXT("hit_r")):FName(TEXT("hit_l")):V.X<0?FName(TEXT("hit_b")):FName(TEXT("hit_f")));}
    else if(Key==EKeys::Delete)Operative->Request(Shift(this)?FName(TEXT("death_back")):FName(TEXT("death_front")));
    else if(Key==EKeys::Enter)Operative->Request(TEXT("respawn"));else if(Key==EKeys::BackSpace){Operative->ResetOperative();Operative->SetActorLocation(FVector(0,0,90));}
    else if(Key==EKeys::Q)Operative->Request(Control(this)?FName(TEXT("pivot_l180")):FName(TEXT("turn_l90")));
    else if(Key==EKeys::E)Operative->Request(Control(this)?FName(TEXT("pivot_r180")):FName(TEXT("turn_r90")));
    else if(Key==EKeys::L)Operative->SetLOD((Operative->ForcedLOD+1)%4);else if(Key==EKeys::T)Operative->SetTeam(1-Operative->TeamIndex);
    else if(Key==EKeys::N)bTeamIcons=!bTeamIcons;
    else if(Key==EKeys::O)Operative->bSkeletonOverlay=!Operative->bSkeletonOverlay;else if(Key==EKeys::M)Operative->SetMaterialMode(Operative->MaterialMode+1);
    else if(Key==EKeys::Y){MoveTarget();bTargetAim=true;}
    else if(Key==EKeys::Equals||Key==EKeys::Add)Operative->Rate=FMath::Min(1.5f,Operative->Rate+.1f);
    else if(Key==EKeys::Hyphen||Key==EKeys::Subtract)Operative->Rate=FMath::Max(.5f,Operative->Rate-.1f);
    return true;
}

TArray<FName> AMorphShowcaseController::FilteredClips() const
{
    TArray<FName> Result;if(!Operative)return Result;
    for(FName Id:Operative->Inventory)if(Search.IsEmpty()||Id.ToString().Contains(Search))Result.Add(Id);
    return Result;
}
void AMorphShowcaseController::SelectClip(FName Id){Operative->ResetOperative();Operative->Request(Id,true);if(Id==TEXT("dialogue"))SetView(3);}
void AMorphShowcaseController::MoveTarget(){if(Targets.Num())Targets[0]->AddActorWorldOffset(FVector(0,Targets[0]->GetActorLocation().Y>0?-360:360,0));}

void AMorphShowcaseController::ToggleInstances()
{
    if(Crowd.Num()){for(AMorphOperative* Actor:Crowd)Actor->Destroy();Crowd.Empty();}
    else for(int32 I=0;I<9;++I)
    {
        FVector Position=FVector(-230-(I/3)*200,-300+(I%3)*220,90);
        AMorphOperative* Actor=GetWorld()->SpawnActor<AMorphOperative>(Position,FRotator(0,15*(I%3),0));Actor->SetTeam(I%2);
        Actor->Request(I%3==0?FName(TEXT("idle_relaxed")):I%3==1?FName(TEXT("channel_loop")):FName(TEXT("walk_f")),true);Crowd.Add(Actor);
    }
    Operative->Trace(FString::Printf(TEXT("instances=%d"),Crowd.Num()+1));
}

void AMorphShowcaseController::StartSequence()
{
    bSequence=true;SequenceTime=0;SequenceStep=0;bBrowser=bFacePanel=false;bTargetAim=false;
    Operative->ResetOperative();Operative->SetActorLocation(FVector(0,0,90));Operative->SetActorRotation(FRotator::ZeroRotator);Operative->Rate=1;
    Operative->Trace(TEXT("deterministic_sequence_begin"));
}

void AMorphShowcaseController::StepSequence(float Delta)
{
    SequenceTime+=Delta;
    const float Times[]={0,1,4,5,6,7,8,10,12,14,15.4f,17,19,21,22,24,26,26.3f,29,32,35,36.2f,38,40,42,45,48,51,55,58,62,66,66.25f,71,75,75.7f,80,84,102,105,106,106.4f,108};
    while(SequenceStep<UE_ARRAY_COUNT(Times) && SequenceTime>=Times[SequenceStep])
    {
        const int32 S=SequenceStep++;
        Operative->Trace(FString::Printf(TEXT("sequence_step=%d sequence_t=%.3f"),S,SequenceTime));
        switch(S)
        {
            case 0:SetView(0);break;
            case 1:Operative->SetMoveInput(FVector2D(-.8f,.6f),1);break;
            case 2:Operative->SetMoveInput(FVector2D(.8f,-.6f),1);Operative->SetAim(-45,20);Operative->Request(TEXT("ranged_fire"));break;
            case 3:Operative->Request(TEXT("ranged_burst"));break;
            case 4:Operative->Request(TEXT("hit_l"));break;
            case 5:Operative->Request(TEXT("cast_directional"));break;
            case 6:Operative->SetMoveInput(FVector2D(-.5f,.7f),0);break;
            case 7:Operative->SetMoveInput(FVector2D::ZeroVector,0);break;
            case 8:Operative->Request(TEXT("dash_f"));break;
            case 9:Operative->Request(TEXT("blink_out"));break;
            case 10:Operative->Request(TEXT("channel_start"));break;
            case 11:Operative->ReleaseState(true);break;
            case 12:Operative->Request(TEXT("channel_start"));break;
            case 13:Operative->ReleaseState(false);break;
            case 14:Operative->Request(TEXT("charge_start"));break;
            case 15:Operative->ReleaseState(false);break;
            case 16:Operative->Request(TEXT("charge_start"));break;
            case 17:Operative->ReleaseState(true);break;
            case 18:Operative->Request(TEXT("reload"));break;
            case 19:Operative->Request(TEXT("deploy"));break;
            case 20:Operative->Request(TEXT("uplink_start"));break;
            case 21:Operative->ReleaseState(true);break;
            case 22:Operative->Request(TEXT("stun_start"));break;
            case 23:Operative->ReleaseState(false);break;
            case 24:Operative->Request(TEXT("sleep_start"));break;
            case 25:Operative->ReleaseState(false);break;
            case 26:Operative->Request(TEXT("knockup_start"));break;
            case 27:Operative->Request(TEXT("knockdown_front"));break;
            case 28:Operative->ReleaseState(false);break;
            case 29:Operative->Request(TEXT("knockdown_back"));break;
            case 30:Operative->ReleaseState(false);break;
            case 31:Operative->Request(TEXT("cast_ground"));break;
            case 32:Operative->Request(TEXT("death_front"));break;
            case 33:Operative->Request(TEXT("respawn"));break;
            case 34:Operative->Request(TEXT("jump_start"));break;
            case 35:Operative->Request(TEXT("death_back"));break;
            case 36:Operative->Request(TEXT("respawn"));break;
            case 37:Operative->ResetOperative();Operative->SetActorLocation(FVector(0,0,90));Operative->SetActorRotation(FRotator::ZeroRotator);Operative->Request(TEXT("dialogue"));SetView(3);break;
            case 38:SetView(0);Operative->Rate=.5f;Operative->Request(TEXT("melee_1"));break;
            case 39:Operative->Rate=1.5f;Operative->Request(TEXT("ranged_burst"));break;
            case 40:Operative->Request(TEXT("jump_start"));break;
            case 41:Operative->SetDisable(TEXT("stasis"));break;
            case 42:Operative->SetDisable(TEXT("stasis"));Operative->Rate=1;bSequence=false;Operative->Trace(TEXT("deterministic_sequence_complete"));if(FParse::Param(FCommandLine::Get(),TEXT("MorphAutoExit")))ConsoleCommand(TEXT("quit"));break;
        }
    }
}

void AMorphShowcaseController::StartPerfCapture()
{
    bPerf=true;PerfTime=0;FrameMs.Empty();GameMs.Empty();RenderMs.Empty();GPUms.Empty();
    PerformancePath=FPaths::Combine(FPaths::ProjectSavedDir(),FString::Printf(TEXT("Verification/performance_%d_instances.csv"),Crowd.Num()+1));
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(PerformancePath),true);
    Operative->Trace(TEXT("performance_begin warmup=5 sample=30 resolution=1920x1080 target_ms=16.667"));
}

void AMorphShowcaseController::FinishPerfCapture()
{
    bPerf=false;FString CSV=TEXT("frame,frame_ms,game_ms,render_ms,gpu_ms,instances\n");
    for(int32 I=0;I<FrameMs.Num();++I)CSV+=FString::Printf(TEXT("%d,%.5f,%.5f,%.5f,%.5f,%d\n"),I,FrameMs[I],GameMs[I],RenderMs[I],GPUms[I],Crowd.Num()+1);
    FFileHelper::SaveStringToFile(CSV,*PerformancePath);
    TArray<double> Sorted=FrameMs;Sorted.Sort();double Sum=0;for(double V:FrameMs)Sum+=V;
    int32 W=0,H=0;GetViewportSize(W,H);const FPlatformMemoryStats Memory=FPlatformMemory::GetStats();
    const FString Summary=FString::Printf(TEXT("{\"instances\":%d,\"frames\":%d,\"warmup_seconds\":5,\"sample_seconds\":30,\"width\":%d,\"height\":%d,\"mean_ms\":%.5f,\"p95_ms\":%.5f,\"p99_ms\":%.5f,\"cpu\":\"%s\",\"physical_ram_gib\":%u,\"process_ram_mib\":%.2f,\"gpu\":\"%s\",\"rhi\":\"%s\",\"screen_percentage\":100,\"vsync\":false,\"generated_frames\":false}\n"),Crowd.Num()+1,FrameMs.Num(),W,H,FrameMs.Num()?Sum/FrameMs.Num():0,Sorted.Num()?Sorted[FMath::Min(Sorted.Num()-1,FMath::FloorToInt(Sorted.Num()*.95))]:0,Sorted.Num()?Sorted[FMath::Min(Sorted.Num()-1,FMath::FloorToInt(Sorted.Num()*.99))]:0,*FPlatformMisc::GetCPUBrand(),FPlatformMemory::GetPhysicalGBRam(),Memory.UsedPhysical/1048576.0,*GRHIAdapterName,GDynamicRHI?GDynamicRHI->GetName():TEXT("none"));
    FFileHelper::SaveStringToFile(Summary,*FPaths::ChangeExtension(PerformancePath,TEXT("json")));
    Operative->Trace(TEXT("performance_complete ")+FPaths::GetCleanFilename(PerformancePath));
    if(FParse::Param(FCommandLine::Get(),TEXT("MorphAutoExit"))&&!bSequence)ConsoleCommand(TEXT("quit"));
}

void AMorphShowcaseController::Click(FName Name)
{
    const FString Id=Name.ToString();
    if(Id.StartsWith(TEXT("clip:"))){SelectClip(FName(*Id.RightChop(5)));return;}
    if(Id.StartsWith(TEXT("state:"))){Operative->SetDisable(FName(*Id.RightChop(6)));return;}
    if(Id.StartsWith(TEXT("action:"))){Operative->Request(FName(*Id.RightChop(7)));return;}
    if(Id.StartsWith(TEXT("face:"))){FaceSelection=FCString::Atoi(*Id.RightChop(5));return;}
    if(Id.StartsWith(TEXT("expression:"))){Operative->SetExpression(FCString::Atoi(*Id.RightChop(11)));return;}
    if(Id==TEXT("browser")){bBrowser=!bBrowser;bFacePanel=false;}
    if(Id==TEXT("next"))BrowserPage++;if(Id==TEXT("prev"))BrowserPage=FMath::Max(0,BrowserPage-1);
    if(Id==TEXT("face_next"))FacePage=(FacePage+1)%4;
    if(Id==TEXT("face_plus")||Id==TEXT("face_minus")){const FName N(FaceNames[FaceSelection]);Operative->SetFace(N,Operative->FaceControls.FindRef(N)+(Id==TEXT("face_plus")?.1f:-.1f));}
    if(Id==TEXT("face_reset"))Operative->FaceReset();
    if(Id==TEXT("face"))SetView(3);if(Id==TEXT("speech")||Id==TEXT("face_speech")){Operative->ResetOperative();Operative->Request(TEXT("dialogue"));SetView(3);}
    if(Id==TEXT("team"))Operative->SetTeam(1-Operative->TeamIndex);if(Id==TEXT("lod"))Operative->SetLOD((Operative->ForcedLOD+1)%4);
    if(Id==TEXT("reset")){Operative->ResetOperative();Operative->SetActorLocation(FVector(0,0,90));}
    if(Id==TEXT("interrupt"))Operative->ReleaseState(true);if(Id==TEXT("finish"))Operative->ReleaseState(false);
    if(Id==TEXT("rate_minus"))Operative->Rate=FMath::Max(.5f,Operative->Rate-.1f);if(Id==TEXT("rate_plus"))Operative->Rate=FMath::Min(1.5f,Operative->Rate+.1f);
    if(Id==TEXT("instances"))ToggleInstances();if(Id==TEXT("sequence"))StartSequence();
    if(Id==TEXT("target")){MoveTarget();bTargetAim=!bTargetAim;}
}

void AMorphShowcaseHUD::Label(const FString& Value,float X,float Y,float Scale,FLinearColor Color)
{DrawText(Value,Color,X,Y,GEngine->GetSmallFont(),Scale,false);}
void AMorphShowcaseHUD::Button(FName Id,const FString& Caption,float X,float Y,float W,float H,bool Active)
{
    DrawRect(Active?FLinearColor(.04,.28,.34,.95):FLinearColor(.05,.08,.11,.95),X,Y,W,H);
    Label(Caption,X+8,Y+5,.95f,Active?FLinearColor(.3,.95,1):FLinearColor(.8,.87,.9));
    AddHitBox(FVector2D(X,Y),FVector2D(W,H),Id,true);
}
void AMorphShowcaseHUD::NotifyHitBoxClick(FName Name){if(auto* C=Cast<AMorphShowcaseController>(GetOwningPlayerController()))C->Click(Name);}

void AMorphShowcaseHUD::DrawHUD()
{
    Super::DrawHUD();auto* C=Cast<AMorphShowcaseController>(GetOwningPlayerController());if(!C||!C->Operative||C->bNoHUD)return;
    AMorphOperative* O=C->Operative;const float W=Canvas->ClipX,H=Canvas->ClipY;
    if(C->bTeamIcons && !C->bFacePanel)
    {
        TArray<AMorphOperative*> Actors;Actors.Add(O);
        for(AMorphOperative* Actor:C->Crowd)Actors.Add(Actor);
        for(AMorphOperative* Actor:Actors)
        {
            FVector2D Screen;
            if(!C->ProjectWorldLocationToScreen(Actor->GetActorLocation()+FVector(0,0,107),Screen)
                || Screen.X<10 || Screen.Y<10 || Screen.X>W-30 || Screen.Y>H-30)continue;
            const bool TeamB=Actor->TeamIndex!=0;
            const FLinearColor Color=TeamB?FLinearColor(1,.32,.12):FLinearColor(.12,.85,1);
            const float X=Screen.X,Y=Screen.Y;
            DrawRect(FLinearColor(.015,.025,.035,.9),X-10,Y-10,33,23);
            if(TeamB)
            {
                DrawLine(X,Y-6,X+6,Y,Color,1.5f);DrawLine(X+6,Y,X,Y+6,Color,1.5f);
                DrawLine(X,Y+6,X-6,Y,Color,1.5f);DrawLine(X-6,Y,X,Y-6,Color,1.5f);
            }
            else
            {
                DrawLine(X,Y-6,X+6,Y+5,Color,1.5f);DrawLine(X+6,Y+5,X-6,Y+5,Color,1.5f);
                DrawLine(X-6,Y+5,X,Y-6,Color,1.5f);
            }
            Label(TeamB?TEXT("B"):TEXT("A"),X+10,Y-7,.8f,FLinearColor::White);
        }
    }
    DrawRect(FLinearColor(.018,.035,.05,.93),12,12,420,177);
    Label(TEXT("MORPHRIG  /  OPERATIVE"),24,22,1.2f,FLinearColor(.3,.9,1));
    Label(O->StateText(),24,50,1.15f);
    Label(FString::Printf(TEXT("clip %s  t %.3f  rate %.2fx"),O->Body.bActive?*O->Body.Id.ToString():*O->GaitTrack.Id.ToString(),O->Body.bActive?O->Body.Time:O->GaitTrack.PreviousTime,O->Rate),24,76);
    Label(FString::Printf(TEXT("speed %.1f cm/s  aim yaw %.1f  pitch %.1f"),O->GetVelocity().Size2D(),O->AimYaw,O->AimPitch),24,98);
    Label(FString::Printf(TEXT("assets %d / 96  LOD %s  team %s  instances %d"),O->Sequences.Num(),O->ForcedLOD==0?TEXT("auto"):*FString::FromInt(O->ForcedLOD-1),O->TeamIndex==0?TEXT("A / triangle"):TEXT("B / diamond"),C->Crowd.Num()+1),24,120);
    Label(O->TeamIndex==0?TEXT("TEAM A   /\\"):TEXT("TEAM B   <>"),24,143,1.1f,O->TeamIndex==0?FLinearColor(.1,.8,1):FLinearColor(1,.3,.1));
    Label(FString::Printf(TEXT("%.1f FPS   %.2f ms"),1/FMath::Max(.0001f,GetWorld()->GetDeltaSeconds()),GetWorld()->GetDeltaSeconds()*1000),250,146);
    for(int32 I=0;I<O->RecentEvents.Num();++I)Label(O->RecentEvents[I],22,204+I*21,.9f,FLinearColor(.66,.76,.81));
    Button(TEXT("browser"),TEXT("B  Animation browser"),12,H-49,208,34,C->bBrowser);
    Button(TEXT("face"),TEXT("F4  Face"),226,H-49,120,34,C->bFacePanel);
    Button(TEXT("speech"),TEXT("Speech"),352,H-49,90,34);
    Button(TEXT("team"),TEXT("T Team"),448,H-49,90,34);
    Button(TEXT("lod"),TEXT("L LOD"),544,H-49,85,34);
    Button(TEXT("instances"),TEXT("F10  1 / 10"),635,H-49,125,34);
    Button(TEXT("sequence"),TEXT("F9 Sequence"),766,H-49,130,34,C->bSequence);
    Button(TEXT("reset"),TEXT("Reset"),902,H-49,85,34);
    if(C->bHelp && !C->bBrowser && !C->bFacePanel)
    {
        DrawRect(FLinearColor(.018,.035,.05,.92),12,H-272,595,206);
        const TCHAR* Help[]={TEXT("WASD move  | Shift run | Ctrl sprint | arrows aim"),TEXT("Space jump | X directional dash | V blink | Q/E turn"),TEXT("LMB shot | F burst | 1/2/3 melee | R reload"),TEXT("G/J/K casts | hold C channel / Z charge / U uplink"),TEXT("I interrupt/cancel | release held key completes | P deploy"),TEXT("H directional hit | Delete death (Shift back) | Enter respawn"),TEXT("F1 third / F2 front / F3 side / F4 face / F5 top"),TEXT("+/- rate | M material | O skeleton | Y target | N team icons"),TEXT("F8 help | F11 warmed frame log | B search all 96 assets")};
        for(int32 I=0;I<UE_ARRAY_COUNT(Help);++I)Label(Help[I],24,H-260+I*21,.95f);
    }
    const float PX=W-390;
    if(C->bBrowser)
    {
        DrawRect(FLinearColor(.018,.035,.05,.98),PX,12,378,H-80);
        Label(TEXT("ANIMATION BROWSER"),PX+14,25,1.2f,FLinearColor(.3,.9,1));
        Label(TEXT("Type a name; Space = _; Backspace edits; Esc closes"),PX+14,56,.83f);
        Label(TEXT("Search: ")+C->Search+TEXT("|"),PX+14,83,1.1f);
        TArray<FName> Rows=C->FilteredClips();const int32 Pages=FMath::Max(1,FMath::DivideAndRoundUp(Rows.Num(),16));C->BrowserPage=FMath::Clamp(C->BrowserPage,0,Pages-1);
        Label(FString::Printf(TEXT("%d results   page %d/%d"),Rows.Num(),C->BrowserPage+1,Pages),PX+14,112);
        for(int32 I=0;I<16 && C->BrowserPage*16+I<Rows.Num();++I)
        {
            const FName Id=Rows[C->BrowserPage*16+I];const FMorphClip* Clip=O->Clip(Id);
            Button(FName(*(TEXT("clip:")+Id.ToString())),Id.ToString()+TEXT("   ")+(Clip?Clip->bPose?TEXT("pose"):Clip->bLoop?TEXT("loop"):TEXT("shot"):TEXT("?")),PX+14,143+I*35,350,30,O->Body.Id==Id&&O->Body.bActive);
        }
        Button(TEXT("prev"),TEXT("PageUp / Previous"),PX+14,710,169,31);Button(TEXT("next"),TEXT("PageDown / Next"),PX+195,710,169,31);
    }
    else if(C->bFacePanel)
    {
        DrawRect(FLinearColor(.018,.035,.05,.97),PX,12,378,H-80);
        Label(TEXT("FACE / INDEPENDENT CONTROLS"),PX+14,25,1.08f,FLinearColor(.3,.9,1));
        const TCHAR* Expr[]={TEXT("neutral"),TEXT("joy"),TEXT("anger"),TEXT("concern"),TEXT("surprise"),TEXT("pain"),TEXT("focus")};
        for(int32 I=0;I<7;++I)Button(FName(*FString::Printf(TEXT("expression:%d"),I)),Expr[I],PX+14+(I%3)*117,59+(I/3)*34,110,29);
        for(int32 I=0;I<8 && C->FacePage*8+I<UE_ARRAY_COUNT(FaceNames);++I)
        {
            const int32 Index=C->FacePage*8+I;const FName N(FaceNames[Index]);
            Button(FName(*FString::Printf(TEXT("face:%d"),Index)),FString::Printf(TEXT("%s    %.2f"),FaceNames[Index],O->FaceControls.FindRef(N)),PX+14,175+I*39,350,34,C->FaceSelection==Index);
        }
        Label(FString::Printf(TEXT("Selected: %s"),FaceNames[C->FaceSelection]),PX+14,500);
        Button(TEXT("face_minus"),TEXT("- 0.10"),PX+14,529,107,31);Button(TEXT("face_plus"),TEXT("+ 0.10"),PX+135,529,107,31);Button(TEXT("face_next"),TEXT("Next 8"),PX+256,529,108,31);
        Button(TEXT("face_reset"),TEXT("Reset facial override"),PX+14,570,350,33);Button(TEXT("face_speech"),TEXT("Play synchronized speech"),PX+14,610,350,33);
        Label(TEXT("Eye ranges -1..1; morphs and visemes 0..1"),PX+14,655,.87f);
        Label(TEXT("Speech resets overrides and plays baked face tracks."),PX+14,678,.83f);
    }
    else
    {
        DrawRect(FLinearColor(.018,.035,.05,.94),PX,12,378,510);
        Label(TEXT("STATE / INTERRUPTION LAB"),PX+14,25,1.1f,FLinearColor(.3,.9,1));
        const TCHAR* States[]={TEXT("stun_start"),TEXT("sleep_start"),TEXT("knockup_start"),TEXT("knockback"),TEXT("knockdown_front"),TEXT("knockdown_back"),TEXT("root"),TEXT("silence"),TEXT("disarm"),TEXT("stasis"),TEXT("fear"),TEXT("charm"),TEXT("taunt"),TEXT("wounded")};
        for(int32 I=0;I<UE_ARRAY_COUNT(States);++I)Button(FName(*(TEXT("state:")+FString(States[I]))),States[I],PX+14+(I%2)*179,61+(I/2)*37,172,31);
        Button(TEXT("finish"),TEXT("Complete / recover"),PX+14,329,172,32);Button(TEXT("interrupt"),TEXT("Interrupt / cancel"),PX+193,329,172,32);
        Button(TEXT("rate_minus"),TEXT("- rate"),PX+14,372,90,31);Button(TEXT("rate_plus"),TEXT("+ rate"),PX+111,372,90,31);Button(TEXT("target"),TEXT("Move / aim target"),PX+208,372,157,31);
        const TCHAR* Actions[]={TEXT("channel_start"),TEXT("charge_start"),TEXT("uplink_start"),TEXT("deploy")};
        for(int32 I=0;I<4;++I)Button(FName(*(TEXT("action:")+FString(Actions[I]))),Actions[I],PX+14+(I%2)*179,414+(I/2)*37,172,31);
    }
    if(C->bPerf)Label(FString::Printf(TEXT("MEASURING %d instances  %.1f/35 s (first 5 s warmup)"),C->Crowd.Num()+1,C->PerfTime),W*.30f,22,1.1f,FLinearColor(.2,1,.5));
}
