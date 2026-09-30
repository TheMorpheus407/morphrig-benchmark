#include "MorphOperative.h"
#include "MorphAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/AudioComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMeshActor.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/Material.h"
#include "Sound/SoundWave.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "DrawDebugHelpers.h"

namespace
{
    bool Begins(FName Id, const TCHAR* Text) { return Id.ToString().StartsWith(Text); }
    bool UpperAction(FName Id) { return Id == TEXT("ranged_fire") || Id == TEXT("ranged_burst") || Id == TEXT("cast_directional"); }
    bool FreeTravel(FName Id) { return Id.IsNone() || Id == TEXT("start_f") || Id == TEXT("stop_f") || Id == TEXT("jump_start") || Id == TEXT("jump_air") || Id == TEXT("fall"); }
    int32 Priority(FName Id)
    {
        if(Begins(Id,TEXT("death_"))||Begins(Id,TEXT("dead_")))return 100;
        if(Begins(Id,TEXT("knockup_")))return 85;
        if(Begins(Id,TEXT("knockdown_"))||Begins(Id,TEXT("prone_"))||Begins(Id,TEXT("getup_")))return 80;
        if(Begins(Id,TEXT("stun_")))return 70;
        if(Begins(Id,TEXT("sleep_")))return 60;
        return 0;
    }
    FString StringField(const TSharedPtr<FJsonObject>& O, const TCHAR* K, const FString& Default = TEXT("")) { FString V; return O->TryGetStringField(K, V) ? V : Default; }
    float NumberField(const TSharedPtr<FJsonObject>& O, const TCHAR* K, float Default) { double V; return O->TryGetNumberField(K, V) ? V : Default; }
    const TCHAR* FaceNames[] = {TEXT("blink_L"),TEXT("blink_R"),TEXT("squint_L"),TEXT("squint_R"),TEXT("brow_raise_L"),TEXT("brow_raise_R"),TEXT("brow_lower_L"),TEXT("brow_lower_R"),TEXT("cheek_L"),TEXT("cheek_R"),TEXT("jaw"),TEXT("lip_close"),TEXT("smile_L"),TEXT("smile_R"),TEXT("frown_L"),TEXT("frown_R"),TEXT("width"),TEXT("pucker"),TEXT("funnel"),TEXT("tongue"),TEXT("eye_yaw_L"),TEXT("eye_yaw_R"),TEXT("eye_pitch_L"),TEXT("eye_pitch_R"),TEXT("viseme_closure"),TEXT("viseme_labiodental"),TEXT("viseme_open"),TEXT("viseme_wide"),TEXT("viseme_round"),TEXT("viseme_tongue"),TEXT("viseme_consonant")};
}

AMorphOperative::AMorphOperative()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(30, 88);
    // CharacterMovement leaves about 2 cm between the collision capsule and
    // floor. Place the authored ground root on the actual floor surface.
    GetMesh()->SetRelativeLocation(FVector(0,0,-90));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->bEnableUpdateRateOptimizations = false;
    GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    GetCharacterMovement()->bOrientRotationToMovement = false;
    GetCharacterMovement()->MaxStepHeight = 20;
    GetCharacterMovement()->SetWalkableFloorAngle(45);
    GetCharacterMovement()->MaxAcceleration = 1200;
    GetCharacterMovement()->BrakingDecelerationWalking = 1700;
    GetCharacterMovement()->JumpZVelocity = 440;
    GetCharacterMovement()->GravityScale = 1.4f;
    bUseControllerRotationYaw = false;
    Voice = CreateDefaultSubobject<UAudioComponent>(TEXT("Dialogue"));
    Voice->SetupAttachment(RootComponent); Voice->bAutoActivate = false;
}

void AMorphOperative::BeginPlay()
{
    Super::BeginPlay();
    TracePath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Verification/state_events.jsonl"));
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(TracePath), true);
    if (USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Operative/SK_Operative.SK_Operative")))
    {
        GetMesh()->SetSkeletalMesh(Mesh);
        GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
        GetMesh()->SetAnimInstanceClass(UMorphAnimInstance::StaticClass());
        for (int32 Slot=0; Slot<GetMesh()->GetNumMaterials(); ++Slot)
            Materials.Add(GetMesh()->CreateDynamicMaterialInstance(Slot));
    }
    LoadLibrary();
    for (const TCHAR* Name : FaceNames) FaceControls.Add(FName(Name),0);
    SetTeam(0);
    BuildPose(0);
    Trace(FString::Printf(TEXT("ready clips=%d height_units=cm"),Sequences.Num()));
}

void AMorphOperative::LoadLibrary()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*FPaths::Combine(FPaths::ProjectContentDir(),TEXT("Data/animation_manifest.json"))))
    { UE_LOG(LogTemp, Error, TEXT("MORPHRIG manifest missing; run tools/import_unreal.py")); return; }
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root) return;
    const TArray<TSharedPtr<FJsonValue>>* Rows;
    if (!Root->TryGetArrayField(TEXT("animations"),Rows)) return;
    for (const TSharedPtr<FJsonValue>& V : *Rows)
    {
        const TSharedPtr<FJsonObject> O=V->AsObject(); if (!O) continue;
        FMorphClip C; C.Id=FName(*StringField(O,TEXT("id"))); C.Form=StringField(O,TEXT("form"));
        C.Layer=StringField(O,TEXT("layer")); C.RootPolicy=StringField(O,TEXT("root_motion_policy"),TEXT("in_place"));
        C.Duration=NumberField(O,TEXT("duration"),1); C.Speed=NumberField(O,TEXT("nominal_speed_cm_s"),0);
        O->TryGetBoolField(TEXT("loop"),C.bLoop); C.bPose=C.Form==TEXT("pose") || Begins(C.Id,TEXT("aim_")) || Begins(C.Id,TEXT("dead_"));
        const TArray<TSharedPtr<FJsonValue>>* Events;
        if (O->TryGetArrayField(TEXT("events"),Events)) for (const TSharedPtr<FJsonValue>& EV : *Events)
        {
            const TSharedPtr<FJsonObject> E=EV->AsObject(); if (!E) continue;
            FMorphMarker M; M.Name=StringField(E,TEXT("name"),StringField(E,TEXT("event")));
            M.Time=NumberField(E,TEXT("time"),NumberField(E,TEXT("frame"),0)/30.f); C.Markers.Add(M);
        }
        C.Markers.Sort([](const FMorphMarker& A,const FMorphMarker& B){return A.Time<B.Time;});
        FString Asset=StringField(O,TEXT("unreal_asset"),TEXT("/Game/Operative/Animations/")+C.Id.ToString());
        if (!Asset.Contains(TEXT("."))) Asset+=TEXT(".")+C.Id.ToString();
        if (UAnimSequence* S=LoadObject<UAnimSequence>(nullptr,*Asset))
        { Sequences.Add(C.Id,S); C.Duration=FMath::Max(.001f,S->GetPlayLength()); }
        else UE_LOG(LogTemp,Error,TEXT("MORPHRIG missing sequence %s"),*Asset);
        Inventory.Add(C.Id); Clips.Add(C.Id,C);
    }
}

UAnimSequence* AMorphOperative::Sequence(FName Id) const { const TObjectPtr<UAnimSequence>* S=Sequences.Find(Id);return S?S->Get():nullptr; }
const FMorphClip* AMorphOperative::Clip(FName Id) const { return Clips.Find(Id); }

void AMorphOperative::Trace(const FString& What)
{
    const FDateTime Now=FDateTime::UtcNow();
    const double Epoch=double(Now.ToUnixTimestamp())+Now.GetMillisecond()/1000.0;
    const FString Line=FString::Printf(TEXT("{\"t\":%.4f,\"epoch\":%.3f,\"actor\":\"%s\",\"state\":\"%s\",\"action\":\"%s\",\"rate\":%.3f,\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}\n"),GetWorld()->GetTimeSeconds(),Epoch,*GetName(),*StateText(),*What,Rate,GetActorLocation().X,GetActorLocation().Y,GetActorLocation().Z);
    FFileHelper::SaveStringToFile(Line,*TracePath,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append);
    UE_LOG(LogTemp,Display,TEXT("MORPHRIG %s"),*Line.TrimEnd());
    RecentEvents.Insert(FString::Printf(TEXT("%6.2f %s"),GetWorld()->GetTimeSeconds(),*What),0);
    if (RecentEvents.Num()>7) RecentEvents.SetNum(7);
}

FString AMorphOperative::StateText() const
{
    if (bStasis) return TEXT("stasis");
    if (Body.bActive) return Body.Id.ToString();
    if (Upper.bActive) return TEXT("locomotion + ")+Upper.Id.ToString();
    if (!AttentionState.IsNone()) return AttentionState.ToString();
    return bWounded?TEXT("wounded"):TEXT("locomotion");
}

bool AMorphOperative::Request(FName Id, bool bBrowser)
{
    if (!Sequence(Id) || !Clip(Id)) {Trace(TEXT("missing ")+Id.ToString());return false;}
    const bool Death=Begins(Id,TEXT("death_")) || Begins(Id,TEXT("dead_"));
    if (!bBrowser && bDead && Id!=TEXT("respawn")) return false;
    if (!bBrowser && bStasis && !Death && Id!=TEXT("respawn")) return false;
    if (!bBrowser && bRooted && (Begins(Id,TEXT("dash_")) || Begins(Id,TEXT("blink_")) || Id==TEXT("jump_start"))) return false;
    if (!bBrowser && bSilenced && (Begins(Id,TEXT("cast_")) || Begins(Id,TEXT("channel_")) || Begins(Id,TEXT("charge_")) || Begins(Id,TEXT("uplink_")))) return false;
    if (!bBrowser && bDisarmed && (Begins(Id,TEXT("melee_")) || Begins(Id,TEXT("ranged_")) || Id==TEXT("reload"))) return false;
    if (!bBrowser && Death && bDead) return false;
    const bool Disable=Begins(Id,TEXT("stun_")) || Begins(Id,TEXT("sleep_")) || Begins(Id,TEXT("knock")) || Begins(Id,TEXT("prone_"));
    if(!bBrowser && Disable && Body.bActive && Priority(Body.Id)>Priority(Id))return false;
    if (!bBrowser && !Death && !Disable && Id!=TEXT("respawn") && Body.bActive && !FreeTravel(Body.Id))
    {
        const bool Follow=(Begins(Id,TEXT("channel_"))&&Begins(Body.Id,TEXT("channel_")))||(Begins(Id,TEXT("charge_"))&&Begins(Body.Id,TEXT("charge_")))||(Begins(Id,TEXT("uplink_"))&&Begins(Body.Id,TEXT("uplink_")))||(Begins(Id,TEXT("stun_"))&&Begins(Body.Id,TEXT("stun_")))||(Begins(Id,TEXT("sleep_"))&&Begins(Body.Id,TEXT("sleep_")))||Begins(Id,TEXT("getup_"));
        if (!Follow) return false;
    }
    bBrowserMode=bBrowser;
    if(Id!=TEXT("blink_out") && Id!=TEXT("blink_in"))GetMesh()->SetHiddenInGame(false);
    if (Death || Disable || Id==TEXT("respawn") || bBrowser)
    {
        Upper=FMorphTrack(); HitTrack=FMorphTrack(); Voice->Stop();
        if (Death) { bDead=true;bStasis=false;StasisVelocity=FVector::ZeroVector;GetCharacterMovement()->SetComponentTickEnabled(true);FaceReset();GetCharacterMovement()->StopMovementImmediately(); }
        if (Id==TEXT("respawn"))
        {
            bDead=bRooted=bSilenced=bDisarmed=bStasis=bWounded=bAimEnabled=false;
            AttentionState=NAME_None;MoveInput=FVector2D::ZeroVector;AimYaw=AimPitch=0;LocomotionPhase=0;
            StasisVelocity=FVector::ZeroVector;
            GetCharacterMovement()->StopMovementImmediately();
            GetCharacterMovement()->SetComponentTickEnabled(true);
            if(DeployedBeacon)DeployedBeacon->Destroy();DeployedBeacon=nullptr;FaceReset();
        }
    }
    FMorphTrack* T = Begins(Id,TEXT("hit_")) && !bBrowser? &HitTrack : UpperAction(Id) && !bBrowser? &Upper : &Body;
    bUpperSnapshot=!bBrowser && (Id==TEXT("stop_f") || T!=&Body);
    if(!bBrowser && Id==TEXT("start_f"))
    {
        const FVector2D Unit=FVector2D(MoveInput.X,-MoveInput.Y).GetSafeNormal();
        const float Lateral=FMath::Abs(Unit.Y);
        const FVector Foot=GetMesh()->GetComponentTransform().InverseTransformPosition(GetMesh()->GetSocketLocation(TEXT("foot_L")));
        const FVector2D Offset(7*Lateral,11.5+9*Lateral);
        const float Along=FVector2D::DotProduct(FVector2D(Foot.X,Foot.Y)-Offset,Unit);
        const bool Sprint=SpeedMode==2 && FMath::Abs(Unit.Y)<.5;
        const FMorphClip* Gait=Clip(Sprint?FName(TEXT("sprint_f")):SpeedMode==0?FName(TEXT("walk_f")):FName(TEXT("run_f")));
        const float Stance=Sprint?.32f:SpeedMode==0?.62f:.37f;
        if(Gait && !Unit.IsNearlyZero())LocomotionPhase=FMath::Fmod(Stance*.5f-Along/(Gait->Speed*Gait->Duration)+1.f,1.f);
        bStationaryContacts=false;
    }
    if(!bBrowser && Id==TEXT("stop_f"))bStationaryContacts=true;
    T->Id=Id;T->Time=0;T->PreviousTime=-.001f;T->Token=NextToken++;T->Cycle=0;T->bActive=true;
    Serial++;TransitionAge=0;FacingCompensation=0;
    if (Id==TEXT("blink_out")) BlinkDestination=GetActorLocation()+GetActorForwardVector()*300;
    if (Id==TEXT("knockup_start") && !bBrowser) LaunchCharacter(FVector(0,0,500),false,true);
    if (Id==TEXT("dialogue"))
    {
        FaceReset();
        if (USoundWave* WAV=LoadObject<USoundWave>(nullptr,TEXT("/Game/Operative/dialogue.dialogue"))) {Voice->SetSound(WAV);Voice->SetPitchMultiplier(Rate);Voice->Play();}
    }
    Trace(FString::Printf(TEXT("enter %s token=%d layer=%s"),*Id.ToString(),T->Token,T==&Upper?TEXT("upper"):T==&HitTrack?TEXT("hit"):TEXT("body")));
    return true;
}

void AMorphOperative::ReleaseState(bool bCancel)
{
    if (bStasis) {SetDisable(TEXT("stasis"));return;}
    if (Begins(Body.Id,TEXT("channel_"))) Request(bCancel?FName(TEXT("channel_interrupt")):FName(TEXT("channel_end")));
    else if (Begins(Body.Id,TEXT("charge_"))) Request(bCancel?FName(TEXT("charge_cancel")):FName(TEXT("charge_release")));
    else if (Begins(Body.Id,TEXT("uplink_"))) Request(bCancel?FName(TEXT("uplink_cancel")):FName(TEXT("uplink_end")));
    else if (Begins(Body.Id,TEXT("stun_"))) Request(TEXT("stun_end"));
    else if (Begins(Body.Id,TEXT("sleep_"))) Request(TEXT("sleep_end"));
    else if (Body.Id==TEXT("prone_front")) Request(TEXT("getup_front"));
    else if (Body.Id==TEXT("prone_back")) Request(TEXT("getup_back"));
    else if (!bDead) {Body=FMorphTrack();Upper=FMorphTrack();Serial++;TransitionAge=0;Voice->Stop();Trace(TEXT("interrupt_to_locomotion"));}
}

void AMorphOperative::ProcessMarker(const FMorphTrack& Track,const FMorphMarker& M)
{
    if(&Track==&Body && !bBrowserMode && (Track.Id==TEXT("start_f")||Track.Id==TEXT("stop_f")) && (M.Name.Contains(TEXT("plant"))||M.Name.StartsWith(TEXT("foot_"))))return;
    Trace(FString::Printf(TEXT("marker %s/%s clip_t=%.4f token=%d cycle=%d"),*Track.Id.ToString(),*M.Name,M.Time,Track.Token,Track.Cycle));
    const FString& Name=M.Name;
    if(Track.Id==TEXT("blink_out") && Name==TEXT("blink_disappear"))
    {GetMesh()->SetHiddenInGame(true);Trace(TEXT("blink_mesh_disappear"));}
    if(Track.Id==TEXT("blink_in") && Name==TEXT("blink_reappear"))
    {GetMesh()->SetHiddenInGame(false);Trace(TEXT("blink_mesh_reappear"));}
    if (Name.Contains(TEXT("muzzle")) || Name.Contains(TEXT("fire")) || Name.Contains(TEXT("cast_release")) || Name.Contains(TEXT("charge_release")))
    {
        FVector Start=GetMesh()->GetSocketLocation(TEXT("emitter_muzzle"));
        FVector Direction=FRotator(AimPitch,GetActorRotation().Yaw-AimYaw,0).Vector();
        DrawDebugLine(GetWorld(),Start,Start+Direction*500,FColor::Cyan,false,.16,0,2);
        DrawDebugSphere(GetWorld(),Start,5,8,FColor::White,false,.16);
    }
    if (Name.Contains(TEXT("hit_start")) || Name.Contains(TEXT("hit_window_open")))
        DrawDebugLine(GetWorld(),GetMesh()->GetSocketLocation(TEXT("blade_base")),GetMesh()->GetSocketLocation(TEXT("blade_tip")),FColor::Orange,false,.2,0,3);
    if ((Name.Contains(TEXT("takeoff")) || Name==TEXT("jump_launch")) && Track.Id==TEXT("jump_start") && !bBrowserMode) Jump();
    if (Name.Contains(TEXT("teleport")) && Track.Id==TEXT("blink_out") && !bBrowserMode)
    {
        FHitResult Sweep;GetCapsuleComponent()->MoveComponent(BlinkDestination-GetActorLocation(),GetActorQuat(),true,&Sweep);
        Trace(TEXT("blink_actor_event"));
    }
    if (Name.Contains(TEXT("release")) && Track.Id==TEXT("deploy") && !DeployedBeacon)
    {
        UStaticMesh* Mesh=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/Operative/SM_Beacon.SM_Beacon"));
        if (Mesh)
        {
            FVector Place=GetMesh()->GetSocketLocation(TEXT("beacon"));
            DeployedBeacon=GetWorld()->SpawnActor<AStaticMeshActor>(Place,GetActorRotation());
            DeployedBeacon->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
            DeployedBeacon->GetStaticMeshComponent()->SetStaticMesh(Mesh);DeployedBeacon->SetActorScale3D(FVector(1));
            DeployedBeacon->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        }
    }
}

void AMorphOperative::AdvanceTrack(FMorphTrack& T,float Delta,bool bRoot)
{
    if (!T.bActive) return;
    const FMorphClip* C=Clip(T.Id);if(!C)return;
    if (C->bPose) {T.Time=0;return;}
    float Remaining=Delta*Rate;
    while (Remaining>0 && T.bActive)
    {
        const float Start=T.Time;
        const float End=FMath::Min(C->Duration,Start+Remaining);
        if (bRoot && C->RootPolicy==TEXT("root_motion") && !bBrowserMode)
        {
            const FTransform Motion=Sequence(T.Id)->ExtractRootMotionFromRange(Start,End,FAnimExtractContext(End,true));
            const FVector Travel=GetMesh()->GetComponentQuat().RotateVector(Motion.GetTranslation());
            FHitResult Hit;GetCharacterMovement()->MoveUpdatedComponent(Travel,GetActorQuat(),true,&Hit);
        }
        T.Time=End;
        for (const FMorphMarker& M:C->Markers) if(M.Time>T.PreviousTime && M.Time<=End)ProcessMarker(T,M);
        T.PreviousTime=End;Remaining-=End-Start;
        if (End>=C->Duration)
        {
            if (C->bLoop) {T.Time=0;T.PreviousTime=-.001f;T.Cycle++;}
            else {CompleteTrack(T);Remaining=0;}
        }
        if (End==Start) break;
    }
}

void AMorphOperative::CompleteTrack(FMorphTrack& T)
{
    const FName Id=T.Id;
    Trace(TEXT("complete ")+Id.ToString());
    T.bActive=false;
    if (&T!=&Body) return;
    if (bBrowserMode && !Begins(Id,TEXT("death_"))) {GetMesh()->SetHiddenInGame(false);bBrowserMode=false;Serial++;TransitionAge=0;return;}
    if (Id==TEXT("channel_start")) Request(TEXT("channel_loop"));
    else if (Id==TEXT("charge_start")) Request(TEXT("charge_hold"));
    else if (Id==TEXT("uplink_start")) Request(TEXT("uplink_loop"));
    else if (Id==TEXT("stun_start")) Request(TEXT("stun_loop"));
    else if (Id==TEXT("sleep_start")) Request(TEXT("sleep_loop"));
    else if (Id==TEXT("knockdown_front")) Request(TEXT("prone_front"));
    else if (Id==TEXT("knockdown_back")) Request(TEXT("prone_back"));
    else if (Id==TEXT("death_front")) Request(TEXT("dead_front"),true);
    else if (Id==TEXT("death_back")) Request(TEXT("dead_back"),true);
    else if (Id==TEXT("jump_start")) {if(!GetCharacterMovement()->IsFalling())Jump();Request(TEXT("jump_air"));}
    else if (Id==TEXT("knockup_start")) Request(TEXT("knockup_air"));
    else if (Id==TEXT("blink_out"))
    {
        Request(TEXT("blink_in"));
    }
    else
    {
        FacingCompensation=0;
        if(Id==TEXT("turn_l90"))FacingCompensation=90;
        if(Id==TEXT("turn_r90"))FacingCompensation=-90;
        if(Id==TEXT("pivot_l180"))FacingCompensation=180;
        if(Id==TEXT("pivot_r180"))FacingCompensation=-180;
        if(FacingCompensation!=0)AddActorWorldRotation(FRotator(0,FacingCompensation,0));
        bUpperSnapshot=Id==TEXT("start_f")||Id==TEXT("stop_f");
        Serial++;TransitionAge=0;
    }
}

void AMorphOperative::Landed(const FHitResult& Floor)
{
    Super::Landed(Floor);
    if(bDead || bBrowserMode || (Body.bActive && !Begins(Body.Id,TEXT("jump_")) && Body.Id!=TEXT("fall") && !Begins(Body.Id,TEXT("knockup_"))))return;
    const bool Heavy=LastVerticalSpeed < -650 || Begins(Body.Id,TEXT("knockup_"));
    Body.bActive=false;Request(Heavy?FName(TEXT("land_heavy")):FName(TEXT("jump_land")));
}

void AMorphOperative::Tick(float Delta)
{
    Super::Tick(Delta);
    if (bStasis) {GetCharacterMovement()->StopMovementImmediately();Voice->SetPaused(true);BuildPose(0);return;}
    Voice->SetPaused(false);Voice->SetPitchMultiplier(Rate);
    TransitionAge+=Delta;
    const bool TravelAllowed=!bDead&&!bRooted&&!bBrowserMode&&(!Body.bActive||FreeTravel(Body.Id));
    FVector2D Input=MoveInput;
    if(AttentionState==TEXT("fear")||AttentionState==TEXT("charm"))
    {
        const FVector Toward=GetActorQuat().UnrotateVector(AttentionTarget-GetActorLocation());
        const float Distance=Toward.Size2D();Input=FVector2D(Toward.X,-Toward.Y).GetSafeNormal();
        if(AttentionState==TEXT("fear")){Input*=-1;SpeedMode=1;if(Distance>800)Input=FVector2D::ZeroVector;}
        else if(Distance<130)Input=FVector2D::ZeroVector;
    }
    if (TravelAllowed && !Input.IsNearlyZero())
    {
        const float Speed=SpeedMode==2?650.f:SpeedMode==1?400.f:150.f;
        GetCharacterMovement()->MaxWalkSpeed=Speed*Rate;
        AddMovementInput(GetActorForwardVector(),Input.X);AddMovementInput(-GetActorRightVector(),Input.Y);
        if(!Body.bActive && GetVelocity().Size2D()<10)Request(TEXT("start_f"));
    }
    if (!TravelAllowed && !GetCharacterMovement()->IsFalling()) GetCharacterMovement()->StopMovementImmediately();
    if(Body.bActive && Body.Id==TEXT("knockback"))
    {FHitResult Sweep;GetCharacterMovement()->MoveUpdatedComponent(-GetActorForwardVector()*Delta*Rate*130,GetActorQuat(),true,&Sweep);}
    if ((!Body.bActive||Body.Id==TEXT("start_f")) && Input.IsNearlyZero() && GetVelocity().Size2D()>25 && !GetCharacterMovement()->IsFalling()) Request(TEXT("stop_f"));
    if (GetCharacterMovement()->IsFalling() && !bDead)
    {
        LastVerticalSpeed=GetVelocity().Z;
        if (Body.Id==TEXT("jump_air") && GetVelocity().Z < -350) Request(TEXT("fall"));
        if (!Body.bActive) Request(TEXT("fall"));
    }
    AdvanceTrack(Body,Delta,true);AdvanceTrack(Upper,Delta,false);AdvanceTrack(HitTrack,Delta,false);
    UpperWeight=FMath::FInterpTo(UpperWeight,Upper.bActive?1.f:0.f,Delta,20.f);
    BuildPose(Delta);
    if (bSkeletonOverlay)
    {
        const FReferenceSkeleton& Ref=GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
        for(int32 I=1;I<Ref.GetNum();++I)DrawDebugLine(GetWorld(),GetMesh()->GetBoneLocation(Ref.GetBoneName(I)),GetMesh()->GetBoneLocation(Ref.GetBoneName(Ref.GetParentIndex(I))),FColor::Green,false,0,0,.7f);
        DrawDebugCapsule(GetWorld(),GetActorLocation(),88,30,GetActorQuat(),FColor::Yellow,false,0,0,1);
    }
}

void AMorphOperative::BuildPose(float Delta)
{
    UMorphAnimInstance* Anim=Cast<UMorphAnimInstance>(GetMesh()->GetAnimInstance());if(!Anim)return;
    FMorphPoseInput& P=Anim->Input;
    const float Speed=GetVelocity().Size2D();
    const FVector ActorPosition=GetActorLocation();
    const float Travel=bHaveGaitLocation&&FVector::DistSquaredXY(ActorPosition,LastGaitActorLocation)<10000?FVector::DistXY(ActorPosition,LastGaitActorLocation):0;
    LastGaitActorLocation=ActorPosition;bHaveGaitLocation=true;
    const FVector Local=GetActorQuat().UnrotateVector(GetVelocity());
    const float Angle=FMath::RadiansToDegrees(FMath::Atan2(-Local.Y,Local.X));
    const float Sector=FMath::Fmod(Angle+360.f,360.f)/45.f;
    const int32 A=FMath::FloorToInt(Sector)%8,B=(A+1)%8;
    const TCHAR* Dirs[]={TEXT("f"),TEXT("fr"),TEXT("r"),TEXT("br"),TEXT("b"),TEXT("bl"),TEXT("l"),TEXT("fl")};
    const FString Prefix=SpeedMode==0?TEXT("walk_"):TEXT("run_");
    FName BaseA=Speed<12?(bWounded?FName(TEXT("idle_wounded")):FName(TEXT("idle_combat"))):FName(*(Prefix+Dirs[A]));
    FName BaseB=Speed<12?BaseA:FName(*(Prefix+Dirs[B]));
    if(SpeedMode==2 && FMath::Abs(Angle)<30 && Speed>12)BaseA=BaseB=TEXT("sprint_f");
    const bool TravelTransition=Body.bActive&&!bBrowserMode&&(Body.Id==TEXT("start_f")||Body.Id==TEXT("stop_f"));
    if(Speed<12 && !LastBaseId.IsNone() && !LastBaseId.ToString().StartsWith(TEXT("idle_")) && !bBrowserMode && (!Body.bActive||TravelTransition))
    {bStationaryContacts=true;bUpperSnapshot=false;Serial++;TransitionAge=0;}
    LastBaseId=BaseA;
    const FMorphClip* CA=Clip(BaseA),*CB=Clip(BaseB);
    if(CA)
    {
        const float SectorFraction=Sector-FMath::FloorToFloat(Sector);
        const float SinA=FMath::Sin(SectorFraction*PI/4),SinB=FMath::Sin((1-SectorFraction)*PI/4);
        // Geometric weights make the interpolated reference velocity point
        // exactly along controller travel between the authored 45-degree axes.
        const float DirectionBlend=BaseA==BaseB?0.f:SinA/(SinA+SinB);
        const FVector2D DirectionA(FMath::Cos(A*PI/4),FMath::Sin(A*PI/4));
        const FVector2D DirectionB(FMath::Cos(B*PI/4),FMath::Sin(B*PI/4));
        const float VirtualScale=FMath::Lerp(DirectionA,DirectionB,DirectionBlend).Size();
        const float Reference=Speed<12?1.f:FMath::Max(1.f,CA->Speed*VirtualScale);
        const float Playback=Speed<12?Rate:Speed/Reference;
        const float OldPhase=LocomotionPhase;
        LocomotionPhase+=(Speed<12?Delta*Playback:Travel/Reference)/CA->Duration;
        if(GaitTrack.Id!=BaseA){GaitTrack.Id=BaseA;GaitTrack.Token=NextToken++;GaitTrack.PreviousTime=FMath::Fmod(OldPhase,1.f)*CA->Duration;GaitTrack.Cycle=FMath::FloorToInt(OldPhase);GaitTrack.bActive=true;}
        if((!Body.bActive||TravelTransition) && Delta>0)
        {
            const float Phase=FMath::Fmod(LocomotionPhase,1.f);
            const float End=Phase*CA->Duration;
            if(FMath::FloorToInt(LocomotionPhase)>GaitTrack.Cycle)
            {for(const FMorphMarker& M:CA->Markers)if(M.Time>GaitTrack.PreviousTime)ProcessMarker(GaitTrack,M);GaitTrack.Cycle=FMath::FloorToInt(LocomotionPhase);GaitTrack.PreviousTime=-.001f;}
            for(const FMorphMarker& M:CA->Markers)if(M.Time>GaitTrack.PreviousTime&&M.Time<=End)ProcessMarker(GaitTrack,M);
            GaitTrack.PreviousTime=End;
        }
        LocomotionPhase=FMath::Fmod(LocomotionPhase,1000.f);
        P.BaseA=Sequence(BaseA);P.BaseB=Sequence(BaseB);P.BaseTimeA=FMath::Fmod(LocomotionPhase,1.f)*CA->Duration;P.BaseTimeB=CB?FMath::Fmod(LocomotionPhase,1.f)*CB->Duration:0;
        P.DirectionAlpha=DirectionBlend;
        P.bTravelGait=Speed>=12;P.GaitReferenceSpeed=Reference;P.GaitActorLocation=ActorPosition;
    }
    P.Body=Body.bActive&&!TravelTransition?Sequence(Body.Id):nullptr;P.BodyTime=Body.Time;
    P.TravelTransition=TravelTransition?Sequence(Body.Id):nullptr;P.TravelTransitionTime=Body.Time;
    P.bContactTransition=TravelTransition||(bStationaryContacts&&!Body.bActive&&Speed<12&&!bBrowserMode);
    P.bUpperSnapshot=bUpperSnapshot;
    P.ResetSerial=ResetSerial;
    P.Upper=Sequence(Upper.Id);P.UpperTime=Upper.Time;P.UpperWeight=UpperWeight;
    P.Hit=HitTrack.bActive?Sequence(HitTrack.Id):nullptr;P.HitTime=HitTrack.Time;
    const FMorphClip* HC=Clip(HitTrack.Id);P.HitWeight=HitTrack.bActive&&HC?FMath::Sin(PI*HitTrack.Time/HC->Duration):0;
    P.Neutral=Sequence(TEXT("idle_combat"));P.NeutralAim=Sequence(TEXT("aim_level_center"));
    const float Y=(AimYaw+60)/60, Z=(AimPitch+35)/35;
    const int32 Y0=FMath::Clamp(FMath::FloorToInt(Y),0,1),Z0=FMath::Clamp(FMath::FloorToInt(Z),0,1);
    const float YF=FMath::Clamp(Y-Y0,0.f,1.f),ZF=FMath::Clamp(Z-Z0,0.f,1.f);
    const TCHAR* Yaws[]={TEXT("left"),TEXT("center"),TEXT("right")};const TCHAR* Pitches[]={TEXT("down"),TEXT("level"),TEXT("up")};
    int32 I=0;for(int32 ZI=0;ZI<2;++ZI)for(int32 YI=0;YI<2;++YI)
    {P.Aim[I]=Sequence(FName(*FString::Printf(TEXT("aim_%s_%s"),Pitches[Z0+ZI],Yaws[Y0+YI])));P.AimWeights[I]=(YI?YF:1-YF)*(ZI?ZF:1-ZF);I++;}
    P.AimWeight=bDead||!bAimEnabled?0:1;P.LookYaw=AimYaw;P.LookPitch=AimPitch;
    P.TransitionSerial=Serial;P.TransitionTime=TransitionAge;P.FacingCompensation=FacingCompensation;P.bFaceOverride=bFaceOverride;P.Face=FaceControls;P.bFrozen=bStasis;P.bBeaconDeployed=DeployedBeacon!=nullptr;
    P.bGroundIK=!bDead&&!bStasis&&!GetCharacterMovement()->IsFalling()&&(!Body.bActive||Body.Id==TEXT("start_f")||Body.Id==TEXT("stop_f")||Begins(Body.Id,TEXT("channel_"))||Begins(Body.Id,TEXT("charge_"))||Begins(Body.Id,TEXT("uplink_"))||UpperAction(Body.Id));
    // The animation proxy traces current authored feet in game-thread
    // PreUpdate, after CharacterMovement, including the transition blend.
    PelvisOffset=Anim->EvaluatedPelvisOffset;
    TMap<FName,float> Effective=FaceControls;
    auto Composite=[&](const TCHAR* N,const TCHAR* Target,float Amount){Effective.FindOrAdd(FName(Target))=FMath::Max(Effective.FindRef(FName(Target)),FaceControls.FindRef(FName(N))*Amount);};
    Composite(TEXT("viseme_closure"),TEXT("lip_close"),1);
    Composite(TEXT("viseme_labiodental"),TEXT("jaw"),.12f);Composite(TEXT("viseme_labiodental"),TEXT("width"),.2f);
    Composite(TEXT("viseme_open"),TEXT("jaw"),.75f);
    Composite(TEXT("viseme_wide"),TEXT("width"),1);Composite(TEXT("viseme_wide"),TEXT("jaw"),.30f);
    Composite(TEXT("viseme_round"),TEXT("pucker"),.85f);Composite(TEXT("viseme_round"),TEXT("jaw"),.30f);
    Composite(TEXT("viseme_tongue"),TEXT("tongue"),1);Composite(TEXT("viseme_tongue"),TEXT("jaw"),.22f);
    Composite(TEXT("viseme_consonant"),TEXT("jaw"),.12f);Composite(TEXT("viseme_consonant"),TEXT("width"),.15f);
    Effective.FindOrAdd(TEXT("jaw"))*=1-FaceControls.FindRef(TEXT("viseme_closure"));
    for(const auto& Pair:Effective)
        if(!Pair.Key.ToString().StartsWith(TEXT("viseme_")))GetMesh()->SetMorphTarget(Pair.Key,bFaceOverride?Pair.Value:0);
    // Match the editable source's bounded bend-driven volume corrections.
    if(USkeletalMesh* Mesh=GetMesh()->GetSkeletalMeshAsset())
    {
        const TCHAR* Bones[]={TEXT("upper_arm_L"),TEXT("upper_arm_R"),TEXT("thigh_L"),TEXT("thigh_R"),TEXT("hand_L"),TEXT("hand_R")};
        const TCHAR* Shapes[]={TEXT("correct_shoulder_L"),TEXT("correct_shoulder_R"),TEXT("correct_hip_L"),TEXT("correct_hip_R"),TEXT("correct_wrist_L"),TEXT("correct_wrist_R")};
        const FReferenceSkeleton& Ref=Mesh->GetRefSkeleton();
        for(int32 J=0;J<6;++J)
        {
            const int32 Bone=Ref.FindBoneIndex(Bones[J]);if(Bone<0)continue;
            const int32 Parent=Ref.GetParentIndex(Bone);if(Parent<0)continue;
            const FTransform BoneLocal=GetMesh()->GetBoneTransform(Bone).GetRelativeTransform(GetMesh()->GetBoneTransform(Parent));
            const FQuat DeltaRotation=Ref.GetRefBonePose()[Bone].GetRotation().Inverse()*BoneLocal.GetRotation();
            const float Bend=FMath::Abs(FMath::DegreesToRadians(DeltaRotation.Rotator().Roll));
            GetMesh()->SetMorphTarget(Shapes[J],FMath::Clamp(Bend-.5f,0.f,1.f));
        }
    }
}

void AMorphOperative::SetMoveInput(FVector2D Value,int32 Mode) {MoveInput=Value.GetClampedToMaxSize(1);SpeedMode=Mode;}
void AMorphOperative::SetAim(float Yaw,float Pitch) {AimYaw=FMath::Clamp(Yaw,-60.f,60.f);AimPitch=FMath::Clamp(Pitch,-35.f,35.f);bAimEnabled=true;}
void AMorphOperative::ResetOperative()
{
    Body=FMorphTrack();Upper=FMorphTrack();HitTrack=FMorphTrack();GaitTrack=FMorphTrack();Voice->Stop();
    GetMesh()->SetHiddenInGame(false);
    bDead=bStasis=bRooted=bSilenced=bDisarmed=bWounded=bBrowserMode=bAimEnabled=false;AttentionState=NAME_None;MoveInput=FVector2D::ZeroVector;FacingCompensation=0;
    LocomotionPhase=0;AimYaw=AimPitch=0;Serial++;TransitionAge=0;
    bHaveGaitLocation=bStationaryContacts=bUpperSnapshot=false;LastBaseId=NAME_None;
    ResetSerial++;
    StasisVelocity=FVector::ZeroVector;
    if(DeployedBeacon)DeployedBeacon->Destroy();DeployedBeacon=nullptr;
    GetCharacterMovement()->SetComponentTickEnabled(true);GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    FaceReset();
    if(GetMesh()->GetAnimInstance()){BuildPose(0);GetMesh()->TickAnimation(0,false);GetMesh()->RefreshBoneTransforms();}
    Trace(TEXT("reset"));
}
void AMorphOperative::SetTeam(int32 Team)
{
    TeamIndex=Team%2;const FLinearColor Color=TeamIndex==0?FLinearColor(.015f,.55f,.8f):FLinearColor(.95f,.12f,.025f);
    for(UMaterialInstanceDynamic* M:Materials)if(M)M->SetVectorParameterValue(TEXT("TeamAccent"),Color);
}
void AMorphOperative::SetLOD(int32 LOD) {ForcedLOD=FMath::Clamp(LOD,0,3);GetMesh()->SetForcedLOD(ForcedLOD);Trace(FString::Printf(TEXT("lod=%d"),ForcedLOD));}
void AMorphOperative::SetMaterialMode(int32 Mode)
{
    MaterialMode=Mode%3;
    for(int32 I=0;I<Materials.Num();++I)
    {
        if(MaterialMode==0)GetMesh()->SetMaterial(I,Materials[I]);
        else if(UMaterial* M=LoadObject<UMaterial>(nullptr,MaterialMode==1?TEXT("/Game/Showcase/M_Normals.M_Normals"):TEXT("/Game/Showcase/M_Clay.M_Clay")))GetMesh()->SetMaterial(I,M);
    }
}
void AMorphOperative::SetFace(FName Name,float Value)
{
    bFaceOverride=true;FaceControls.Add(Name,FMath::Clamp(Value,Name.ToString().StartsWith(TEXT("eye_"))?-1.f:0.f,1.f));
}
void AMorphOperative::FaceReset() {bFaceOverride=false;for(auto& Pair:FaceControls)Pair.Value=0;GetMesh()->ClearMorphTargets();}
void AMorphOperative::SetExpression(int32 Index)
{
    FaceReset();bFaceOverride=true;
    if(Index==1){SetFace(TEXT("smile_L"),.8);SetFace(TEXT("smile_R"),.75);SetFace(TEXT("cheek_L"),.5);SetFace(TEXT("cheek_R"),.5);}
    if(Index==2){SetFace(TEXT("brow_lower_L"),.9);SetFace(TEXT("brow_lower_R"),.9);SetFace(TEXT("squint_L"),.45);SetFace(TEXT("squint_R"),.45);SetFace(TEXT("frown_L"),.5);}
    if(Index==3){SetFace(TEXT("brow_raise_L"),.7);SetFace(TEXT("brow_lower_R"),.2);SetFace(TEXT("frown_L"),.7);SetFace(TEXT("frown_R"),.65);}
    if(Index==4){SetFace(TEXT("brow_raise_L"),1);SetFace(TEXT("brow_raise_R"),1);SetFace(TEXT("jaw"),.6);SetFace(TEXT("funnel"),.3);}
    if(Index==5){SetFace(TEXT("blink_L"),.85);SetFace(TEXT("squint_R"),.8);SetFace(TEXT("brow_lower_L"),.8);SetFace(TEXT("frown_R"),.75);}
    if(Index==6){SetFace(TEXT("squint_L"),.4);SetFace(TEXT("squint_R"),.4);SetFace(TEXT("brow_lower_L"),.35);SetFace(TEXT("lip_close"),.8);}
}
void AMorphOperative::SetDisable(FName Name)
{
    if(Name==TEXT("root"))bRooted=!bRooted;
    else if(Name==TEXT("silence")){bSilenced=!bSilenced;if(bSilenced&&(Begins(Body.Id,TEXT("channel_"))||Begins(Body.Id,TEXT("charge_"))||Begins(Body.Id,TEXT("uplink_"))||Begins(Body.Id,TEXT("cast_"))))ReleaseState(true);if(bSilenced&&Upper.Id==TEXT("cast_directional"))Upper.bActive=false;}
    else if(Name==TEXT("disarm")){bDisarmed=!bDisarmed;if(bDisarmed&&Begins(Upper.Id,TEXT("ranged_")))Upper.bActive=false;if(bDisarmed&&(Begins(Body.Id,TEXT("melee_"))||Body.Id==TEXT("reload")))ReleaseState(true);}
    else if(Name==TEXT("stasis"))
    {
        bStasis=!bStasis;
        if(bStasis){StasisVelocity=GetVelocity();GetCharacterMovement()->StopMovementImmediately();}
        else GetCharacterMovement()->Velocity=StasisVelocity;
        GetCharacterMovement()->SetComponentTickEnabled(!bStasis);
    }
    else if(Name==TEXT("wounded"))bWounded=!bWounded;
    else if(Name==TEXT("fear")||Name==TEXT("charm")||Name==TEXT("taunt"))AttentionState=AttentionState==Name?NAME_None:Name;
    else Request(Name);
    Trace(TEXT("status ")+Name.ToString());
}
