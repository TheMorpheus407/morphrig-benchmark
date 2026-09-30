#include "MorphRig.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "TwoBoneIK.h"

// Native animation graph: compressed authored sequences -> directional travel blend ->
// continuous aim grid -> interruptible upper/full body action -> additive impacts -> terrain IK.
struct FMorphAnimProxy : FAnimInstanceProxy {
    AMorphOperative* Actor=nullptr;
    explicit FMorphAnimProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}
    virtual void PreUpdate(UAnimInstance* Instance,float Dt) override {
        FAnimInstanceProxy::PreUpdate(Instance,Dt);
        Actor=Cast<AMorphOperative>(Instance->GetOwningActor());
    }
    void Sample(FPoseContext& Out,const FString& Id,float Time) const {
        Out.ResetToRefPose();
        if(!Actor) return;
        if(UAnimSequence* Seq=Actor->Sequence(Id)) {
            FAnimationPoseData Data(Out);
            FAnimExtractContext Context(FMath::Clamp(double(Time),0.0,double(Seq->GetPlayLength())),false);
            Seq->GetAnimationPose(Data,Context);
            if(const FMorphClip* C=Actor->Clip(Id); C && C->RootPolicy=="root_motion" && Out.Pose.GetNumBones()>0) {
                FCompactPoseBoneIndex Root(0);
                Out.Pose[Root].SetTranslation(FVector::ZeroVector);
            }
        }
    }
    bool Upper(const FName Name,const FReferenceSkeleton& Ref,int32 Bone) const {
        int32 B=Bone;
        while(B>=0) {
            if(Ref.GetBoneName(B)==FName("spine_01")) return true;
            B=Ref.GetParentIndex(B);
        }
        return false;
    }
    void Blend(FPoseContext& Out,const FPoseContext& Other,float Weight,bool UpperOnly) const {
        const auto& BC=Out.Pose.GetBoneContainer();
        const auto& Ref=BC.GetReferenceSkeleton();
        for(FCompactPoseBoneIndex I : Out.Pose.ForEachBoneIndex()) {
            const int32 MeshBone=BC.MakeMeshPoseIndex(I).GetInt();
            if(!UpperOnly || Upper(Ref.GetBoneName(MeshBone),Ref,MeshBone)) {
                Out.Pose[I].Blend(Out.Pose[I],Other.Pose[I],Weight);
                Out.Pose[I].NormalizeRotation();
            }
        }
    }
    void Terrain(FPoseContext& Out) const {
        if(!Actor || Actor->GetCharacterMovement()==nullptr || Actor->BrowserMode || Actor->IsTerminal() ||
           Actor->ActionId.Contains("jump") || Actor->ActionId.Contains("knock") || Actor->ActionId.Contains("prone") ||
           Actor->ActionId.Contains("getup") || Actor->ActionId.Contains("sleep") || Actor->ActionId.Contains("death")) return;
        const auto& BC=Out.Pose.GetBoneContainer();
        auto Find=[&](FName Name) { FString Mapped=Name.ToString().Replace(TEXT("."),TEXT("_"));return BC.GetCompactPoseIndexFromSkeletonIndex(BC.GetSkeletonAsset()->GetReferenceSkeleton().FindBoneIndex(FName(*Mapped))); };
        TArray<FTransform> CS; CS.SetNum(Out.Pose.GetNumBones());
        for(FCompactPoseBoneIndex I:Out.Pose.ForEachBoneIndex()) {
            auto P=BC.GetParentBoneIndex(I);
            CS[I.GetInt()]=P.IsValid()? Out.Pose[I]*CS[P.GetInt()]:Out.Pose[I];
        }
        auto Pelvis=Find("pelvis");
        if(Pelvis.IsValid()) {
            auto Parent=BC.GetParentBoneIndex(Pelvis);
            FVector Offset=Parent.IsValid()?CS[Parent.GetInt()].GetRotation().UnrotateVector(FVector(0,0,Actor->PelvisCorrection)):FVector(0,0,Actor->PelvisCorrection);
            Out.Pose[Pelvis].AddToTranslation(Offset);
            for(auto I:Out.Pose.ForEachBoneIndex()) {auto P=BC.GetParentBoneIndex(I);CS[I.GetInt()]=P.IsValid()?Out.Pose[I]*CS[P.GetInt()]:Out.Pose[I];}
        }
        for(int Side=0;Side<2;Side++) {
            const FString S=Side==0?".L":".R";
            auto Hip=Find(FName(*("thigh"+S))), Knee=Find(FName(*("shin"+S))), Ankle=Find(FName(*("foot"+S)));
            if(!Hip.IsValid() || !Knee.IsValid() || !Ankle.IsValid()) continue;
            float Z=Side==0?Actor->FootOffsetL:Actor->FootOffsetR;
            FTransform H=CS[Hip.GetInt()],K=CS[Knee.GetInt()],A=CS[Ankle.GetInt()];
            FVector Target=A.GetLocation()+FVector(0,0,Z-Actor->PelvisCorrection);
            FVector LimbAxis=(A.GetLocation()-H.GetLocation()).GetSafeNormal();
            FVector KneeProjection=H.GetLocation()+LimbAxis*FVector::DotProduct(K.GetLocation()-H.GetLocation(),LimbAxis);
            FVector Bend=(K.GetLocation()-KneeProjection).GetSafeNormal();
            if(Bend.IsNearlyZero())Bend=FVector::ForwardVector;
            FVector Pole=K.GetLocation()+Bend*70;
            AnimationCore::SolveTwoBoneIK(H,K,A,Pole,Target,false,1.0,1.0);
            const auto Parent=BC.GetParentBoneIndex(Hip);
            Out.Pose[Hip]=H.GetRelativeTransform(CS[Parent.GetInt()]);
            Out.Pose[Knee]=K.GetRelativeTransform(H);
            // Keep authored ankle pitch on level ground; add the bounded support normal on ramp.
            FVector Normal=Side==0?Actor->FootNormalL:Actor->FootNormalR;
            FQuat Tilt=FQuat::FindBetweenNormals(FVector::UpVector,Normal);
            A.SetRotation(Tilt*A.GetRotation());
            Out.Pose[Ankle]=A.GetRelativeTransform(K);
            Out.Pose[Hip].NormalizeRotation(); Out.Pose[Knee].NormalizeRotation(); Out.Pose[Ankle].NormalizeRotation();
        }
    }
    virtual bool Evaluate(FPoseContext& Out) override {
        if(!Actor || !Actor->Room) { Out.ResetToRefPose(); return true; }
        FPoseContext AimTarget(this),AimReference(this);
        bool HasAim=Actor->SmoothAimWeight>0.001f && !Actor->BrowserMode;
        Sample(Out,Actor->BaseId,Actor->BaseTime);
        if(Actor->BaseBlend<1) {
            FPoseContext Old(this); Sample(Old,Actor->PreviousBaseId,Actor->PreviousBaseTime);
            Blend(Old,Out,Actor->BaseBlend,false); Out.Pose.CopyBonesFrom(Old.Pose);
        }
        if(Actor->ActionId.IsEmpty() && !Actor->PreviousActionId.IsEmpty() && Actor->ActionBlend<1) {
            FPoseContext Exit(this);Sample(Exit,Actor->PreviousActionId,Actor->PreviousActionTime);
            Blend(Exit,Out,Actor->ActionBlend,false);Out.Pose.CopyBonesFrom(Exit.Pose);
        }
        if(HasAim) {
            float X=FMath::Clamp(Actor->SmoothAimYaw/60.f,-1.f,1.f), Y=FMath::Clamp(Actor->SmoothAimPitch/35.f,-1.f,1.f);
            FString XName=X<0?"left":"right",YName=Y<0?"down":"up";
            FPoseContext Center(this),H(this),V(this),Corner(this);
            Sample(Center,"aim_level_center",0); Sample(H,"aim_level_"+XName,0);
            Sample(AimReference,"aim_level_center",0);
            Sample(V,"aim_"+YName+"_center",0); Sample(Corner,"aim_"+YName+"_"+XName,0);
            Blend(Center,H,FMath::Abs(X),true); Blend(V,Corner,FMath::Abs(X),true);
            Blend(Center,V,FMath::Abs(Y),true);AimTarget.Pose.CopyBonesFrom(Center.Pose);
            const auto* Current=Actor->Clip(Actor->ActionId);
            if(!Current || !Current->Layer.Contains("upper"))Blend(Out,Center,Actor->SmoothAimWeight,true);
        }
        if(!Actor->ActionId.IsEmpty()) {
            const auto* C=Actor->Clip(Actor->ActionId);
            bool UpperOnly=C && C->Layer.Contains("upper") && !Actor->BrowserMode;
            FPoseContext Action(this); Sample(Action,Actor->ActionId,Actor->ActionTime);
            if(Actor->ActionBlend<1 && !Actor->PreviousActionId.IsEmpty()) {
                FPoseContext Prev(this);Sample(Prev,Actor->PreviousActionId,Actor->PreviousActionTime);
                Blend(Prev,Action,Actor->ActionBlend,UpperOnly);Action.Pose.CopyBonesFrom(Prev.Pose);
                Blend(Out,Action,1,UpperOnly);
            } else Blend(Out,Action,Actor->ActionBlend,UpperOnly);
        }
        if(!Actor->HitId.IsEmpty()) {
            FPoseContext Hit(this),RefPose(this); Sample(Hit,Actor->HitId,Actor->HitTime); Sample(RefPose,Actor->HitId,0);
            const auto& BC=Out.Pose.GetBoneContainer();const auto& Ref=BC.GetReferenceSkeleton();
            const auto* C=Actor->Clip(Actor->HitId);float W=C?FMath::Sin(PI*FMath::Clamp(Actor->HitTime/C->Duration,0.f,1.f)):0;
            for(auto I:Out.Pose.ForEachBoneIndex()) {
                const int32 B=BC.MakeMeshPoseIndex(I).GetInt();if(!Upper(Ref.GetBoneName(B),Ref,B)) continue;
                FQuat Delta=Hit.Pose[I].GetRotation()*RefPose.Pose[I].GetRotation().Inverse();
                Out.Pose[I].SetRotation((FQuat::Slerp(FQuat::Identity,Delta,W)*Out.Pose[I].GetRotation()).GetNormalized());
            }
        }
        // Calibrated local deltas from the authored aim grid preserve action wrist recoil/cast keys.
        if(!Actor->ActionId.IsEmpty() && HasAim) {
            const auto* C=Actor->Clip(Actor->ActionId);
            if(C && C->Layer.Contains("upper")) {
                const auto& BC=Out.Pose.GetBoneContainer();const auto& Ref=BC.GetReferenceSkeleton();
                for(auto I:Out.Pose.ForEachBoneIndex()) {
                    const int32 B=BC.MakeMeshPoseIndex(I).GetInt();if(!Upper(Ref.GetBoneName(B),Ref,B))continue;
                    FQuat Offset=AimTarget.Pose[I].GetRotation()*AimReference.Pose[I].GetRotation().Inverse();
                    Out.Pose[I].SetRotation((FQuat::Slerp(FQuat::Identity,Offset,Actor->SmoothAimWeight)*Out.Pose[I].GetRotation()).GetNormalized());
                }
            }
        }
        Terrain(Out);
        for(FString S:{".L",".R"}) {
            const auto& BC=Out.Pose.GetBoneContainer();
            auto Eye=BC.GetCompactPoseIndexFromSkeletonIndex(BC.GetSkeletonAsset()->GetReferenceSkeleton().FindBoneIndex(FName(*("eye"+S.Replace(TEXT("."),TEXT("_"))))));
            if(Eye.IsValid()) {
                float Yaw=Actor->FaceControls.FindRef("eye_yaw"+S)*25;
                float PitchControl=Actor->FaceControls.FindRef("eye_pitch"+S);
                float Pitch=PitchControl*12;
                // Imported eye rest axes: local X = up, Y = left, Z = forward.
                // Rotate around X for yaw and Y for pitch; Z would only roll the iris.
                FQuat Offset=FQuat(FVector::ForwardVector,FMath::DegreesToRadians(Yaw))*FQuat(FVector::RightVector,FMath::DegreesToRadians(Pitch));
                // A bounded 2.4 mm socket correction keeps the stylized iris behind
                // the lid at vertical look extremes. Authored gaze has zero correction.
                Out.Pose[Eye].AddToTranslation(Out.Pose[Eye].GetRotation().RotateVector(FVector(0,0,-.24f*FMath::Abs(PitchControl))));
                Out.Pose[Eye].SetRotation((Out.Pose[Eye].GetRotation()*Offset).GetNormalized());
            }
        }
        return true;
    }
};

UMorphAnimInstance::UMorphAnimInstance() { bUseMultiThreadedAnimationUpdate=false; }
FAnimInstanceProxy* UMorphAnimInstance::CreateAnimInstanceProxy() { return new FMorphAnimProxy(this); }
void UMorphAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete Proxy; }
