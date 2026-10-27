#include "MorphAuditLibrary.h"

#include "Animation/Skeleton.h"
#include "Animation/AnimSequence.h"
#include "ReferenceSkeleton.h"
#include "Animation/MorphTarget.h"
#include "Components/SkinnedMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"

static FString MorphPoint(const FVector3f& Point)
{
    return FString::Printf(TEXT("[%.6f,%.6f,%.6f]"), Point.X, Point.Y, Point.Z);
}

FString UMorphAuditLibrary::DescribeBindPose(USkeletalMesh* Mesh)
{
    if (!Mesh) return TEXT("{}");
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    FString Output = FString::Printf(TEXT("{\"bone_count\":%d,\"inverse_count\":%d,\"bones\":["), Ref.GetNum(), Mesh->GetRefBasesInvMatrix().Num());
    for (int32 Index = 0; Index < Ref.GetNum(); ++Index)
    {
        if (Index) Output += TEXT(",");
        const FMatrix44f& Inverse = Mesh->GetRefBasesInvMatrix()[Index];
        Output += FString::Printf(TEXT("{\"index\":%d,\"name\":\"%s\",\"parent\":%d,\"local\":\"%s\",\"inverse_matrix\":%s,\"inverse_translation\":%s}"), Index, *Ref.GetBoneName(Index).ToString(), Ref.GetParentIndex(Index), *Ref.GetRefBonePose()[Index].ToString(), *FString::Printf(TEXT("\"%s\""), *Inverse.ToString()), *MorphPoint(Inverse.GetOrigin()));
    }
    return Output + TEXT("]}");
}

FString UMorphAuditLibrary::DescribeSkinnedGeometry(USkinnedMeshComponent* Component)
{
    USkeletalMesh* Mesh = Component ? Cast<USkeletalMesh>(Component->GetSkinnedAsset()) : nullptr;
    if (!Mesh) return TEXT("{}");
    const int32 LOD = FMath::Max(0, Component->GetPredictedLODLevel());
    const FSkeletalMeshRenderData* Data = Mesh->GetResourceForRendering();
    FSkinWeightVertexBuffer* Weights = Component->GetSkinWeightBuffer(LOD);
    if (!Data || !Data->LODRenderData.IsValidIndex(LOD) || !Weights) return TEXT("{}");
    const FSkeletalMeshLODRenderData& LODData = Data->LODRenderData[LOD];
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    auto Matrix = [](const FMatrix44f& Value) { return FString::Printf(TEXT("\"%s\""), *Value.ToString()); };
    FString Output = FString::Printf(TEXT("{\"lod\":%d,\"component_transform\":\"%s\",\"bones\":{"), LOD, *Component->GetComponentTransform().ToString());
    for (const FName Name : { TEXT("root"), TEXT("pelvis"), TEXT("head"), TEXT("eye_L"), TEXT("eye_R"), TEXT("thigh_L"), TEXT("shin_L"), TEXT("foot_L"), TEXT("hand_L") })
    {
        Output += FString::Printf(TEXT("\"%s\":{\"evaluated\":\"%s\",\"reference\":\"%s\"},"), *Name.ToString(), *Component->GetBoneTransform(Name).ToString(), *GetMeshBoneRestTransform(Mesh, Name).ToString());
    }
    Output.RemoveFromEnd(TEXT(","));
    Output += TEXT("},\"sections\":[");
    for (int32 SectionIndex = 0; SectionIndex < LODData.RenderSections.Num(); ++SectionIndex)
    {
        const FSkelMeshRenderSection& Section = LODData.RenderSections[SectionIndex];
        if (SectionIndex) Output += TEXT(",");
        Output += FString::Printf(TEXT("{\"section\":%d,\"material\":%d,\"bone_map\":%d,\"vertices\":%d,\"samples\":["), SectionIndex, Section.MaterialIndex, Section.BoneMap.Num(), Section.GetNumVertices());
        const uint32 Base = Section.GetVertexBufferIndex();
        for (uint32 Sample = 0; Sample < FMath::Min<uint32>(6, Section.GetNumVertices()); ++Sample)
        {
            const uint32 Vertex = Base + Sample;
            const FVector3f Position = LODData.StaticVertexBuffers.PositionVertexBuffer.VertexPosition(Vertex);
            const FVector3f Skinned = USkeletalMeshComponent::GetSkinnedVertexPosition(Cast<USkeletalMeshComponent>(Component), Vertex, LODData, *Weights);
            if (Sample) Output += TEXT(",");
            Output += FString::Printf(TEXT("{\"vertex\":%u,\"reference\":%s,\"skinned\":%s,\"world\":%s,\"influences\":["), Vertex, *MorphPoint(Position), *MorphPoint(Skinned), *MorphPoint(FVector3f(Component->GetComponentTransform().TransformPosition(FVector(Skinned)))));
            const FSkinWeightInfo Info = Weights->GetVertexSkinWeights(Vertex);
            bool bHasInfluence = false;
            for (int32 Influence = 0; Influence < Weights->GetMaxBoneInfluences(); ++Influence)
            {
                if (!Info.InfluenceWeights[Influence]) continue;
                bHasInfluence = true;
                const int32 MapIndex = Info.InfluenceBones[Influence];
                const int32 Bone = Section.BoneMap.IsValidIndex(MapIndex) ? Section.BoneMap[MapIndex] : INDEX_NONE;
                if (Bone == INDEX_NONE)
                {
                    Output += FString::Printf(TEXT("{\"bone\":\"INVALID\",\"weight\":%u,\"map_index\":%d,\"bone_index\":-1},"), Info.InfluenceWeights[Influence], MapIndex);
                    continue;
                }
                const FMatrix44f RefToLocal = Mesh->GetRefBasesInvMatrix()[Bone] * FMatrix44f(Component->GetComponentSpaceTransforms()[Bone].ToMatrixWithScale());
                Output += FString::Printf(TEXT("{\"bone\":\"%s\",\"weight\":%u,\"map_index\":%d,\"bone_index\":%d,\"matrix\":\"%s\",\"component_matrix\":%s,\"skin_matrix\":%s,\"manual_skinned\":%s},"), *Ref.GetRefBoneInfo()[Bone].Name.ToString(), Info.InfluenceWeights[Influence], MapIndex, Bone, *Component->GetComponentSpaceTransforms()[Bone].ToString(), *Matrix(FMatrix44f(Component->GetComponentSpaceTransforms()[Bone].ToMatrixWithScale())), *Matrix(RefToLocal), *MorphPoint(RefToLocal.TransformPosition(Position)));
            }
            if (bHasInfluence) Output.RemoveFromEnd(TEXT(","));
            Output += TEXT("]}");
        }
        Output += TEXT("]}");
    }
    return Output + TEXT("]}");
}

bool UMorphAuditLibrary::SetNotifyName(UAnimSequence* Sequence, UAnimNotify* Notify, const FName EventName)
{
    if (!Sequence || !Notify) return false;
    for (FAnimNotifyEvent& Event : Sequence->Notifies)
    {
        if (Event.Notify == Notify)
        {
            Event.NotifyName = EventName;
            Sequence->Modify();
            Sequence->MarkPackageDirty();
            return true;
        }
    }
    return false;
}

int32 UMorphAuditLibrary::GetLODTriangleCount(USkeletalMesh* Mesh, const int32 LODIndex)
{
    if (!Mesh)
    {
        return -1;
    }
    const FSkeletalMeshRenderData* RenderData = Mesh->GetResourceForRendering();
    if (!RenderData || !RenderData->LODRenderData.IsValidIndex(LODIndex))
    {
        return -1;
    }
    return RenderData->LODRenderData[LODIndex].GetTotalFaces();
}

int32 UMorphAuditLibrary::GetDeformationBoneCount(USkeletalMesh* Mesh)
{
    return Mesh && Mesh->GetSkeleton() ? Mesh->GetSkeleton()->GetReferenceSkeleton().GetNum() : 0;
}

int32 UMorphAuditLibrary::GetLODMorphTargetCount(USkeletalMesh* Mesh, const int32 LODIndex)
{
    if (!Mesh) return -1;
    int32 Count = 0;
    for (const TObjectPtr<UMorphTarget>& Target : Mesh->GetMorphTargets())
    {
        if (Target && Target->GetNumDeltasForLOD(LODIndex) > 0) ++Count;
    }
    return Count;
}

bool UMorphAuditLibrary::SetMaterialSlots(USkeletalMesh* Mesh, const TArray<UMaterialInterface*>& Materials)
{
#if WITH_EDITOR
    if (!Mesh || Materials.IsEmpty() || Mesh->GetMaterials().Num() != Materials.Num()) return false;
    for (const UMaterialInterface* Material : Materials) if (!Material) return false;
    TArray<FSkeletalMaterial> Slots;
    Slots.Reserve(Materials.Num());
    for (int32 Index = 0; Index < Materials.Num(); ++Index)
    {
        FSkeletalMaterial Slot = Mesh->GetMaterials()[Index];
        Slot.MaterialInterface = Materials[Index];
        Slots.Add(Slot);
    }
    Mesh->Modify();
    Mesh->SetMaterials(Slots);
    Mesh->MarkPackageDirty();
    for (int32 Index = 0; Index < Materials.Num(); ++Index)
    {
        if (Mesh->GetMaterials()[Index].MaterialInterface != Materials[Index]) return false;
    }
    return true;
#else
    return false;
#endif
}

bool UMorphAuditLibrary::RebindSkeletonForCleanup(UObject* Asset, USkeleton* Skeleton)
{
    if (!Asset || !Skeleton) return false;
    if (UAnimSequence* Sequence = Cast<UAnimSequence>(Asset))
    {
        Sequence->SetSkeleton(Skeleton);
        return Sequence->GetSkeleton() == Skeleton;
    }
    if (USkeletalMesh* Mesh = Cast<USkeletalMesh>(Asset))
    {
        Mesh->SetSkeleton(Skeleton);
        return Mesh->GetSkeleton() == Skeleton;
    }
    return false;
}

FVector UMorphAuditLibrary::GetRootMotionDelta(UAnimSequence* Sequence, const double StartTime, const float DeltaSeconds)
{
    if (!Sequence) return FVector::ZeroVector;
    const FTransform Start = Sequence->ExtractRootTrackTransform(FAnimExtractContext(StartTime, true), nullptr);
    const FTransform End = Sequence->ExtractRootTrackTransform(FAnimExtractContext(StartTime + DeltaSeconds, true), nullptr);
    return End.GetTranslation() - Start.GetTranslation();
}

bool UMorphAuditLibrary::GetLowestSkinnedBoneZ(USkinnedMeshComponent* Component, const FName BoneName, float& OutMinZ)
{
    USkeletalMeshComponent* Skeletal = Cast<USkeletalMeshComponent>(Component);
    USkeletalMesh* Mesh = Skeletal ? Skeletal->GetSkeletalMeshAsset() : nullptr;
    if (!Mesh) return false;
    const int32 BoneIndex = Mesh->GetRefSkeleton().FindBoneIndex(BoneName);
    const int32 LOD = FMath::Max(0, Skeletal->GetPredictedLODLevel());
    const FSkeletalMeshRenderData* Data = Mesh->GetResourceForRendering();
    FSkinWeightVertexBuffer* Weights = Skeletal->GetSkinWeightBuffer(LOD);
    if (BoneIndex == INDEX_NONE || !Data || !Data->LODRenderData.IsValidIndex(LOD) || !Weights) return false;
    const FSkeletalMeshLODRenderData& LODData = Data->LODRenderData[LOD];
    OutMinZ = TNumericLimits<float>::Max();
    for (const FSkelMeshRenderSection& Section : LODData.RenderSections)
    {
        for (uint32 LocalVertex = 0; LocalVertex < Section.GetNumVertices(); ++LocalVertex)
        {
            const uint32 Vertex = Section.GetVertexBufferIndex() + LocalVertex;
            const FSkinWeightInfo Info = Weights->GetVertexSkinWeights(Vertex);
            bool bInfluenced = false;
            for (int32 Influence = 0; Influence < Weights->GetMaxBoneInfluences(); ++Influence)
            {
                const int32 MapIndex = Info.InfluenceBones[Influence];
                if (Info.InfluenceWeights[Influence] && Section.BoneMap.IsValidIndex(MapIndex) && Section.BoneMap[MapIndex] == BoneIndex)
                {
                    bInfluenced = true;
                    break;
                }
            }
            if (bInfluenced) OutMinZ = FMath::Min(OutMinZ, USkeletalMeshComponent::GetSkinnedVertexPosition(Skeletal, Vertex, LODData, *Weights).Z);
        }
    }
    return OutMinZ != TNumericLimits<float>::Max();
}

FTransform UMorphAuditLibrary::GetMeshBoneRestTransform(USkeletalMesh* Mesh, const FName BoneName)
{
    if (!Mesh) return FTransform::Identity;
    const FReferenceSkeleton& Reference = Mesh->GetRefSkeleton();
    const int32 BoneIndex = Reference.FindBoneIndex(BoneName);
    if (BoneIndex == INDEX_NONE) return FTransform::Identity;
    TArray<FTransform> Component;
    Component.SetNum(Reference.GetNum());
    for (int32 Index = 0; Index < Reference.GetNum(); ++Index)
    {
        const int32 Parent = Reference.GetParentIndex(Index);
        Component[Index] = Parent == INDEX_NONE ? Reference.GetRefBonePose()[Index] : Reference.GetRefBonePose()[Index] * Component[Parent];
    }
    return Component[BoneIndex];
}

bool UMorphAuditLibrary::AlignRootReferenceToAnimation(USkeletalMesh* Mesh, UAnimSequence* Sequence)
{
#if WITH_EDITOR
    USkeleton* Skeleton = Mesh ? Mesh->GetSkeleton() : nullptr;
    if (!Mesh || !Skeleton || !Sequence || Sequence->GetSkeleton() != Skeleton || Mesh->GetRefSkeleton().FindBoneIndex(TEXT("root")) != 0)
    {
        return false;
    }
    const FTransform AnimationRoot = Sequence->ExtractRootTrackTransform(FAnimExtractContext(0.0, false), nullptr);
    if (AnimationRoot.ContainsNaN())
    {
        return false;
    }
    Mesh->Modify();
    Skeleton->Modify();
    FTransform Corrected = Mesh->GetRefSkeleton().GetRefBonePose()[0];
    Corrected.SetRotation(AnimationRoot.GetRotation());
    FReferenceSkeletonModifier Modifier(Mesh->GetRefSkeleton(), Skeleton);
    Modifier.UpdateRefPoseTransform(0, Corrected);
    Mesh->GetRefBasesInvMatrix().Reset();
    Mesh->CalculateInvRefMatrices();
    Skeleton->UpdateReferencePoseFromMesh(Mesh);
    Mesh->PostEditChange();
    Skeleton->PostEditChange();
    return true;
#else
    return false;
#endif
}

bool UMorphAuditLibrary::AlignAnimationRootToReference(USkeletalMesh* SourceMesh, USkeletalMesh* TargetMesh, const TArray<UAnimSequence*>& Sequences)
{
#if WITH_EDITOR
    USkeleton* SourceSkeleton = SourceMesh ? SourceMesh->GetSkeleton() : nullptr;
    USkeleton* TargetSkeleton = TargetMesh ? TargetMesh->GetSkeleton() : nullptr;
    if (!SourceSkeleton || !TargetSkeleton || SourceSkeleton != TargetSkeleton || Sequences.IsEmpty()) return false;
    const FReferenceSkeleton& Reference = TargetSkeleton->GetReferenceSkeleton();
    if (Reference.FindBoneIndex(TEXT("root")) != 0) return false;
    const FQuat RootRotation = Reference.GetRefBonePose()[0].GetRotation();
    for (UAnimSequence* Sequence : Sequences)
    {
        IAnimationDataModel* DataModel = Sequence ? Sequence->GetDataModel() : nullptr;
        if (!DataModel || Sequence->GetSkeleton() != TargetSkeleton || DataModel->GetNumBoneTracks() != Reference.GetNum()) return false;
        const int32 CurveCount = DataModel->GetNumberOfFloatCurves();
        TArray<FTransform> Keys;
        DataModel->GetBoneTrackTransforms(TEXT("root"), Keys);
        if (Keys.IsEmpty()) return false;
        const FQuat RootFrameDelta = (RootRotation * Keys[0].GetRotation().Inverse()).GetNormalized();
        TArray<FVector3f> Positions;
        TArray<FQuat4f> Rotations;
        TArray<FVector3f> Scales;
        for (const FTransform& Key : Keys)
        {
            if (Key.ContainsNaN()) return false;
            Positions.Add(FVector3f(RootFrameDelta.RotateVector(Key.GetLocation())));
            Rotations.Add(FQuat4f((RootFrameDelta * Key.GetRotation()).GetNormalized()));
            Scales.Add(FVector3f(Key.GetScale3D()));
        }
        Sequence->Modify();
        if (!Sequence->GetController().SetBoneTrackKeys(TEXT("root"), Positions, Rotations, Scales, false)) return false;
        if (DataModel->GetNumBoneTracks() != Reference.GetNum() || DataModel->GetNumberOfFloatCurves() != CurveCount) return false;
        Sequence->MarkPackageDirty();
    }
    return true;
#else
    return false;
#endif
}
