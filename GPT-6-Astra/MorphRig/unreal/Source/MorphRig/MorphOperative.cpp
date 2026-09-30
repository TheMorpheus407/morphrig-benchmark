#include "MorphRig.h"
#include "Animation/AnimSequence.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/AudioComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundWave.h"
#include "DrawDebugHelpers.h"
#include "Dom/JsonObject.h"

AMorphOperative::AMorphOperative() {
    PrimaryActorTick.bCanEverTick=true;
    GetCapsuleComponent()->InitCapsuleSize(29,90);
    GetMesh()->SetRelativeLocation(FVector(0,0,-92.15f));
    GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
    GetMesh()->SetAnimInstanceClass(UMorphAnimInstance::StaticClass());
    GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    GetMesh()->bEnableUpdateRateOptimizations=false;
    GetCharacterMovement()->MaxWalkSpeed=150;
    GetCharacterMovement()->JumpZVelocity=410;
    GetCharacterMovement()->GravityScale=1.25;
    GetCharacterMovement()->MaxStepHeight=20;
    GetCharacterMovement()->SetWalkableFloorAngle(45);
    GetCharacterMovement()->bOrientRotationToMovement=false;
    GetCharacterMovement()->BrakingDecelerationWalking=1700;
    bUseControllerRotationYaw=false;
    Voice=CreateDefaultSubobject<UAudioComponent>("DialogueVoice");Voice->SetupAttachment(GetRootComponent());Voice->bAutoActivate=false;
    AccentIcon=CreateDefaultSubobject<UStaticMeshComponent>("TeamIdentity");AccentIcon->SetupAttachment(GetRootComponent());
    AccentIcon->SetCollisionEnabled(ECollisionEnabled::NoCollision);AccentIcon->SetRelativeLocation(FVector(0,0,99));
    Beacon=CreateDefaultSubobject<UStaticMeshComponent>("ReleasedBeacon");Beacon->SetupAttachment(GetRootComponent());Beacon->SetCollisionEnabled(ECollisionEnabled::NoCollision);Beacon->SetVisibility(false);
}
void AMorphOperative::BeginPlay() {
    Super::BeginPlay();
    USkeletalMesh* Mesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/Operative/SK_Operative.SK_Operative"));
    if(Mesh) { GetMesh()->SetSkeletalMeshAsset(Mesh);GetMesh()->SetAnimInstanceClass(UMorphAnimInstance::StaticClass()); }
    if(auto* Asset=GetMesh()->GetSkeletalMeshAsset())for(int32 I=0;I<Asset->GetLODNum();I++)if(auto* Info=Asset->GetLODInfo(I))Info->ScreenSize.Default=I==0?1.f:I==1?.45f:.18f;
    GetMesh()->MarkRenderStateDirty();
    AccentIcon->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
    AccentIcon->SetRelativeScale3D(FVector(.12,.12,.025));
    Beacon->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Game/Operative/SM_Beacon.SM_Beacon")));
    SetTeam(false);
}
UAnimSequence* AMorphOperative::Sequence(const FString& Id) const { return Room?Room->Sequences.FindRef(Id):nullptr; }
const FMorphClip* AMorphOperative::Clip(const FString& Id) const { return Room?Room->Clips.Find(Id):nullptr; }
bool AMorphOperative::IsTerminal() const { return Dead || ActionId.StartsWith("death") || ActionId.StartsWith("dead_"); }
bool AMorphOperative::TranslationAllowed() const {
    if(Stasis || IsTerminal() || Disable=="root" || Disable=="stun" || Disable=="sleep") return false;
    if(ActionId.IsEmpty()) return true;
    if(ActionId.StartsWith("jump") || ActionId=="fall" || ActionId=="start_f" || ActionId=="stop_f")return true;
    if(const auto* C=Clip(ActionId)) return C->Layer=="upper_body" || C->Layer=="additive_upper";
    return false;
}
void AMorphOperative::SetLocomotion(const FString& Id) {
    if(BaseId==Id) return;
    PreviousBaseId=BaseId;PreviousBaseTime=BaseTime;BaseId=Id;
    float Phase=0;if(const auto* Prev=Clip(PreviousBaseId)) Phase=PreviousBaseTime/FMath::Max(.01f,Prev->Duration);
    BaseTime=0;if(const auto* New=Clip(BaseId);New && New->NominalSpeed>0) BaseTime=Phase*New->Duration;
    BaseBlend=0;
}
void AMorphOperative::Emit(const FString& Name,const FString& Id,float At) {
    LastEvent=FString::Printf(TEXT("%s @ %.3fs"),*Name,At);
    if(Name.Contains("muzzle") || Name.Contains("cast_release") || Name.Contains("hit_window"))EventFlash=.18f;
    if(InstanceNumber==0 && Room) Room->Trace(FString::Printf(TEXT("event generation=%llu loop=%d clip=%s t=%.3f marker=%s"),ActionGeneration,LoopCounter,*Id,At,*Name));
    if(Name=="cell_grip" || Name=="cell_extract")CellInHand=true;
    if(Name=="cell_insert" || Name=="cell_release")CellInHand=false;
    if(Name=="beacon_release" && !BeaconReleased && Beacon->GetStaticMesh()) {
        BeaconReleased=true;
        FTransform Placement=GetMesh()->GetSocketTransform("beacon",RTS_World);
        Beacon->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        Beacon->SetWorldTransform(Placement);Beacon->SetVisibility(true);
        GetMesh()->HideBoneByName("beacon",EPhysBodyOp::PBO_None);
        if(Room && InstanceNumber==0) {
            const FBox Box=Beacon->CalcBounds(Placement).GetBox();
            Room->Trace(FString::Printf(TEXT("beacon_world scale=%s min_cm=%s max_cm=%s materials=%d"),*Placement.GetScale3D().ToCompactString(),*Box.Min.ToCompactString(),*Box.Max.ToCompactString(),Beacon->GetNumMaterials()));
        }
    }
    if(Name.Contains("teleport") && Id=="blink_out" && !BlinkTeleported && Disable!="root") {AddActorWorldOffset(GetActorForwardVector()*250,true);BlinkTeleported=true;GetMesh()->SetVisibility(false);}
}
void AMorphOperative::AdvanceEvents(const FString& Id,float Old,float Now,bool Wrap) {
    const auto* C=Clip(Id);if(!C)return;
    for(int32 I=0;I<C->Events.Num();I++) {
        const auto& E=C->Events[I];
        bool Crossed=Wrap?(E.Time>Old || E.Time<=Now):(E.Time>Old && E.Time<=Now);
        if(Old<=0 && E.Time==0) Crossed=true;
        FString Key=FString::Printf(TEXT("%llu/%s/%d/%d"),ActionGeneration,*Id,LoopCounter,I);
        if(Crossed && !FiredEvents.Contains(Key)) { FiredEvents.Add(Key);Emit(E.Name,Id,E.Time); }
    }
}
static int32 Priority(const FString& Id) {
    if(Id.StartsWith("death")||Id.StartsWith("dead_"))return 100;
    if(Id=="respawn")return 95;
    if(Id.StartsWith("knock")||Id.StartsWith("prone")||Id.StartsWith("getup"))return 80;
    if(Id.StartsWith("stun"))return 70;
    if(Id.StartsWith("sleep"))return 60;
    if(Id.StartsWith("jump")||Id=="fall"||Id=="land_heavy")return 50;
    if(Id.StartsWith("channel_")||Id.StartsWith("charge_")||Id.StartsWith("uplink_"))return 30;
    return 20;
}
void AMorphOperative::Request(const FString& Id,bool FromBrowser) {
    if(!Sequence(Id)) { if(Room)Room->Trace("missing asset "+Id);return; }
    if(FromBrowser) { ResetOperative();BrowserMode=true; }
    if(!FromBrowser) {
        if(Stasis && !Id.StartsWith("death") && Id!="respawn") return;
        if(Disable=="root" && (Id.StartsWith("dash_") || Id.StartsWith("blink_") || Id=="jump_start"))return;
        if(IsTerminal() && Id!="respawn" && !Id.StartsWith("dead_"))return;
        if(Disable=="silence" && (Id.StartsWith("cast_")||Id.StartsWith("channel_")||Id.StartsWith("charge_")))return;
        if(Disable=="disarm" && (Id.StartsWith("melee_")||Id.StartsWith("ranged_")))return;
        if(Id.StartsWith("hit_")) { HitId=Id;HitTime=0;Emit("impact",Id,0);return; }
        if(!ActionId.IsEmpty() && Priority(Id)<Priority(ActionId) && Id!="respawn")return;
        BrowserMode=false;
    }
    if(Id!="blink_out")GetMesh()->SetVisibility(true);
    if(Id=="deploy") {BeaconReleased=false;Beacon->SetVisibility(false);GetMesh()->UnHideBoneByName("beacon");}
    if(Id=="respawn") { Dead=false;Stasis=false;Disable="none";CellInHand=false;BeaconReleased=false;Beacon->SetVisibility(false);GetMesh()->UnHideBoneByName("beacon");GetMesh()->SetVisibility(true); }
    PreviousActionId=ActionId;PreviousActionTime=ActionTime;ActionId=Id;ActionTime=0;ActionBlend=0;
    ActionOrigin=GetActorLocation();
    if(Room && Id.StartsWith("dash_"))Room->Trace(FString::Printf(TEXT("dash_start %s actor=%s"),*Id,*ActionOrigin.ToCompactString()));
    if(Id=="blink_out")BlinkTeleported=false;
    if(Id=="blink_in")GetMesh()->SetVisibility(true);
    ActionGeneration++;FiredEvents.Empty();LoopCounter=0;
    if(Id.StartsWith("death")) { Dead=true;Stasis=false;Paused=false;Disable="none";GetCharacterMovement()->SetMovementMode(MOVE_Walking);GetCharacterMovement()->StopMovementImmediately();Voice->Stop(); }
    if(Id.StartsWith("knockdown")||Id.StartsWith("stun")||Id.StartsWith("sleep"))GetCharacterMovement()->StopMovementImmediately();
    if(Id.StartsWith("dash_"))GetCharacterMovement()->StopMovementImmediately();
    if(Id=="knockup_start") {LaunchCharacter(FVector(0,0,650),true,true);JumpClock=0;}
    if(Id=="dialogue" && Room && Room->Dialogue) { ActionRate=1;Voice->SetSound(Room->Dialogue);Voice->Play(); }
    if(Id!="dialogue")Voice->Stop();
    if(Room && InstanceNumber==0)Room->Trace(FString::Printf(TEXT("state generation=%llu %s -> %s priority=%d browser=%d"),ActionGeneration,*PreviousActionId,*Id,Priority(Id),int(FromBrowser)));
}
void AMorphOperative::FinishAction(const FString& Id) {
    if(Id.StartsWith("dash_") && Room)Room->Trace(FString::Printf(TEXT("dash_end %s actor=%s horizontal_cm=%.4f"),*Id,*GetActorLocation().ToCompactString(),FVector::Dist2D(GetActorLocation(),ActionOrigin)));
    if(BrowserMode) { ActionTime=FMath::Max(0.f,Clip(Id)->Duration-.0001f);Paused=true;return; }
    FString Next;
    if(Id=="channel_start")Next="channel_loop";
    else if(Id=="charge_start")Next="charge_hold";
    else if(Id=="uplink_start")Next="uplink_loop";
    else if(Id=="stun_start")Next="stun_loop";
    else if(Id=="sleep_start")Next="sleep_loop";
    else if(Id=="knockup_start")Next="knockup_air";
    else if(Id=="knockdown_front")Next="prone_front";
    else if(Id=="knockdown_back")Next="prone_back";
    else if(Id=="death_front")Next="dead_front";
    else if(Id=="death_back")Next="dead_back";
    else if(Id=="jump_start") { if(Disable!="root")Jump();Next="jump_air"; }
    else if(Id=="blink_out") { if(!BlinkTeleported && Disable!="root"){AddActorWorldOffset(GetActorForwardVector()*250,true);BlinkTeleported=true;}Next="blink_in"; }
    else if(Id=="respawn") { Dead=false;Stasis=false;Disable="none"; }
    else if(Id.StartsWith("turn_") || Id.StartsWith("pivot_")) {
        float Turn=Id.Contains("l")?-1:1;Turn*=Id.StartsWith("pivot")?180:90;
        Facing+=Turn;SetActorRotation(FRotator(0,Facing,0));
        PreviousActionId.Empty();ActionId.Empty();ActionTime=0;ActionBlend=1;return;
    }
    if(!Next.IsEmpty()) {
        // Internal transitions are allowed to step down the priority ladder.
        FString Previous=ActionId;float T=ActionTime;ActionId.Empty();Request(Next);PreviousActionId=Previous;PreviousActionTime=T;
    } else {
        if(Id.StartsWith("dead_")) {ActionTime=Clip(Id)->Duration;return;}
        PreviousActionId=ActionId;PreviousActionTime=ActionTime;ActionId.Empty();ActionTime=0;ActionBlend=0;CellInHand=false;
    }
}
void AMorphOperative::StopAction(bool Interrupt) {
    if(IsTerminal())return;
    FString Next;
    if(ActionId.StartsWith("channel_"))Next=Interrupt?"channel_interrupt":"channel_end";
    else if(ActionId.StartsWith("charge_"))Next=Interrupt?"charge_cancel":"charge_release";
    else if(ActionId.StartsWith("uplink_"))Next=Interrupt?"uplink_cancel":"uplink_end";
    else if(ActionId.StartsWith("stun")) { Disable="none";Next="stun_end"; }
    else if(ActionId.StartsWith("sleep")) { Disable="none";Next="sleep_end"; }
    else if(ActionId=="prone_front")Next="getup_front";
    else if(ActionId=="prone_back")Next="getup_back";
    else if(ActionId=="knockup_air")Next="knockdown_back";
    if(!Next.IsEmpty()) Request(Next);
}
void AMorphOperative::ResetOperative() {
    Voice->Stop();Dead=false;Paused=false;Stasis=false;BrowserMode=false;Disable="none";ActionId.Empty();PreviousActionId.Empty();HitId.Empty();
    AimYaw=AimPitch=AimWeight=SmoothAimYaw=SmoothAimPitch=SmoothAimWeight=0;LastEvent="ready";
    SetLocomotion("idle_relaxed");BaseTime=0;ActionTime=0;CellInHand=false;BeaconReleased=false;FaceControls.Empty();FacePreset="neutral";
    Beacon->SetVisibility(false);GetMesh()->UnHideBoneByName("beacon");
    GetCharacterMovement()->SetMovementMode(MOVE_Walking);GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(FVector(0,InstanceNumber*130,100));Facing=0;SetActorRotation(FRotator::ZeroRotator);GetMesh()->SetVisibility(true);
    if(Room && InstanceNumber==0)Room->Trace("reset living props=home");
}
void AMorphOperative::SetTeam(bool Alternate) {
    TeamB=Alternate;DynamicMaterials.Empty();
    for(int32 I=0;I<GetMesh()->GetNumMaterials();I++) {
        auto* Mat=GetMesh()->CreateAndSetMaterialInstanceDynamic(I);if(!Mat)continue;
        Mat->SetVectorParameterValue("TeamColor",Alternate?FLinearColor(1,.28,.04):FLinearColor(.02,.7,.8));
        DynamicMaterials.Add(Mat);
    }
    AccentIcon->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,Alternate?TEXT("/Engine/BasicShapes/Sphere.Sphere"):TEXT("/Engine/BasicShapes/Cube.Cube")));
    for(int32 I=0;I<Beacon->GetNumMaterials();I++)if(auto* Mat=Beacon->CreateAndSetMaterialInstanceDynamic(I))Mat->SetVectorParameterValue("TeamColor",Alternate?FLinearColor(1,.28,.04):FLinearColor(.02,.7,.8));
    if(auto* Accent=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Operative/M_TeamAccent.M_TeamAccent"))) {
        AccentIcon->SetMaterial(0,Accent);
        if(auto* M=AccentIcon->CreateAndSetMaterialInstanceDynamic(0))M->SetVectorParameterValue("TeamColor",Alternate?FLinearColor(1,.25,.02):FLinearColor(.02,.7,.8));
    }
}
void AMorphOperative::UpdateFace(float Dt) {
    if(!Room)return;
    TMap<FString,float> Values=FaceControls;
    FString FaceId=ActionId.IsEmpty()?BaseId:ActionId;float FaceTime=ActionId.IsEmpty()?BaseTime:ActionTime;
    if(Room->FaceClipCurves.Contains(FaceId)) {
        for(const auto& Pair:Room->FaceClipCurves[FaceId]) {
            float Value=0;const auto& Keys=Pair.Value;
            for(int32 I=0;I<Keys.Num();I++) {
                if(Keys[I].X>FaceTime) {
                    if(I>0)Value=FMath::Lerp(Keys[I-1].Y,Keys[I].Y,(FaceTime-Keys[I-1].X)/FMath::Max(.001f,Keys[I].X-Keys[I-1].X));
                    break;
                }
                Value=Keys[I].Y;
            }
            Values.FindOrAdd(Pair.Key)=FMath::Max(Value,Values.FindRef(Pair.Key));
        }
    }
    for(const FString& N:Room->MorphNames) {
        float Target=Values.FindRef(N);float& Current=FaceLast.FindOrAdd(N);
        Current=FMath::FInterpTo(Current,Target,Dt,20);GetMesh()->SetMorphTarget(FName(*N),Current);
    }
}
void AMorphOperative::Tick(float Dt) {
    Super::Tick(Dt);if(!Room)return;
    EventFlash=FMath::Max(0.f,EventFlash-Dt);
    Voice->SetPaused(Paused || Stasis);
    if(Paused || Stasis) { GetCharacterMovement()->StopMovementImmediately();GetMesh()->GlobalAnimRateScale=0;return; }
    GetMesh()->GlobalAnimRateScale=1;
    SmoothAimYaw=FMath::FInterpTo(SmoothAimYaw,AimYaw,Dt,12);
    SmoothAimPitch=FMath::FInterpTo(SmoothAimPitch,AimPitch,Dt,12);
    SmoothAimWeight=FMath::FInterpTo(SmoothAimWeight,AimWeight,Dt,12);
    float Step=Dt*ActionRate;
    const FVector Velocity=GetVelocity();
    if(!BrowserMode) {
        FString Travel=Wounded?"idle_wounded":"idle_combat";
        if(Velocity.Size2D()>10 && !GetCharacterMovement()->IsFalling()) {
            FVector Local=GetActorTransform().InverseTransformVectorNoScale(Velocity);
            float Angle=FMath::RadiansToDegrees(FMath::Atan2(Local.Y,Local.X));
            int32 D=(FMath::RoundToInt(Angle/45.f)+8)%8;
            static const TCHAR* Correct[]={TEXT("f"),TEXT("fr"),TEXT("r"),TEXT("br"),TEXT("b"),TEXT("bl"),TEXT("l"),TEXT("fl")};
            Travel=(Velocity.Size2D()>220?"run_":"walk_")+FString(Correct[D]);
            if(Velocity.Size2D()>520 && D==0)Travel="sprint_f";
        }
        SetLocomotion(Travel);
        if(ActionId.IsEmpty() && !GetCharacterMovement()->IsFalling()) {
            if(Velocity.Size2D()>18 && LastVelocity.Size2D()<=18)Request("start_f");
            else if(Velocity.Size2D()<12 && LastVelocity.Size2D()>=12)Request("stop_f");
        }
        if(ActionId=="jump_air" || ActionId=="fall") {
            JumpClock+=Dt;
            if(GetCharacterMovement()->IsFalling())LastAirVelocity=Velocity.Z;
            if(JumpClock>.15 && !GetCharacterMovement()->IsFalling()) { FString Land=LastAirVelocity< -650?"land_heavy":"jump_land";ActionId.Empty();Request(Land);JumpClock=0; }
            else if(Velocity.Z< -250 && ActionId=="jump_air") { ActionId.Empty();Request("fall"); }
        }
        if(ActionId=="knockup_air" && !GetCharacterMovement()->IsFalling()) {ActionId.Empty();Request("knockdown_back");}
        if(GetCharacterMovement()->IsFalling() && ActionId.IsEmpty()) {Request("fall");JumpClock=0;}
    }
    if(const auto* B=Clip(BaseId)) {
        float SpeedScale=B->NominalSpeed>0?FMath::Clamp(Velocity.Size2D()/B->NominalSpeed,.5f,1.5f):1;
        float Old=BaseTime;BaseTime+=(B->NominalSpeed>0?Dt:Step)*SpeedScale;bool Wrap=BaseTime>B->Duration;
        if(Wrap) {BaseTime=FMath::Fmod(BaseTime,B->Duration);LoopCounter++;}AdvanceEvents(BaseId,Old,BaseTime,Wrap);
    }
    if(const auto* B=Clip(PreviousBaseId))PreviousBaseTime=FMath::Fmod(PreviousBaseTime+Step,B->Duration);
    BaseBlend=FMath::Min(1.f,BaseBlend+Dt/0.16f);ActionBlend=FMath::Min(1.f,ActionBlend+Dt/0.12f);
    if(!ActionId.IsEmpty()) {
        FString Id=ActionId;const auto* C=Clip(Id);
        if(C) {
            float Old=ActionTime;ActionTime+=Step;
            if(C->RootPolicy=="root_motion" && Disable!="root") {
                if(auto* Seq=Sequence(Id)) {
                    FAnimExtractContext EC(ActionTime,true);
                    FTransform Delta=Seq->ExtractRootMotionFromRange(Old,FMath::Min(ActionTime,C->Duration),EC);
                    AddActorWorldOffset(GetActorRotation().RotateVector(Delta.GetTranslation()),true);
                }
            }
            if(Id=="knockback")AddActorWorldOffset(-GetActorForwardVector()*Dt*125,true);
            bool Wrap=C->Loop && ActionTime>C->Duration;
            if(Wrap) {ActionTime=FMath::Fmod(ActionTime,C->Duration);LoopCounter++;}
            AdvanceEvents(Id,Old,FMath::Min(ActionTime,C->Duration),Wrap);
            if(!C->Loop && ActionTime>=C->Duration)FinishAction(Id);
        }
    }
    if(!HitId.IsEmpty()) { HitTime+=Step;if(const auto* H=Clip(HitId);H && HitTime>=H->Duration)HitId.Empty(); }
    for(int32 S=0;S<2;S++) {
        FName Bone=S==0?"foot_L":"foot_R";FVector Foot=GetMesh()->GetSocketLocation(Bone);
        FHitResult Hit;FCollisionQueryParams Params;Params.AddIgnoredActor(this);
        float Target=0;FVector Normal=FVector::UpVector;
        if(GetWorld()->LineTraceSingleByChannel(Hit,Foot+FVector(0,0,40),Foot-FVector(0,0,55),ECC_Visibility,Params) && !GetCharacterMovement()->IsFalling()) {
            (S==0?GroundHeightL:GroundHeightR)=Hit.ImpactPoint.Z;
            // The baked ankle height is 11 cm. Preserve airborne gait clearance; solve only near contacts.
            float Desired=Hit.ImpactPoint.Z-GetMesh()->GetComponentLocation().Z + 11.f*(1.f/FMath::Max(.8f,Hit.ImpactNormal.Z)-1.f);
            if(Desired> -25 && Desired<28)Target=FMath::Clamp(Desired,-22.f,22.f);
            Normal=GetMesh()->GetComponentTransform().InverseTransformVectorNoScale(Hit.ImpactNormal);
        }
        float& Offset=S==0?FootOffsetL:FootOffsetR;Offset=Target;
        (S==0?FootNormalL:FootNormalR)=Normal;
    }
    float SupportDrop=FMath::Min(0.f,FMath::Min(FootOffsetL,FootOffsetR));
    PelvisCorrection=SupportDrop<PelvisCorrection?SupportDrop:FMath::FInterpTo(PelvisCorrection,SupportDrop,Dt,12);
    UpdateFace(Dt);
    if(ShowBones) {
        auto& Ref=GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
        for(int32 B=1;B<Ref.GetNum();B++)DrawDebugLine(GetWorld(),GetMesh()->GetBoneLocation(Ref.GetBoneName(B)),GetMesh()->GetBoneLocation(Ref.GetBoneName(Ref.GetParentIndex(B))),FColor(20,255,220),false,0,SDPG_Foreground,1.f);
    }
    if(EventFlash>0)DrawDebugSphere(GetWorld(),GetMesh()->GetSocketLocation("emitter_muzzle"),4,8,FColor::Cyan,false,0,0,1);
    LastVelocity=Velocity;
}
