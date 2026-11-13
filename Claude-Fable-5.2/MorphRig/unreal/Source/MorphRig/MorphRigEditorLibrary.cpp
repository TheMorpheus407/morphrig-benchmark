#include "MorphRigEditorLibrary.h"
#include "MorphRig.h"
#include "MorphEventNotify.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Animation/Skeleton.h"
#include "Animation/AnimSequence.h"
#include "AnimationRuntime.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "ReferenceSkeleton.h"
#include "Animation/MorphTarget.h"

static bool ComponentSpaceRefPose(USkeletalMesh* Mesh, TArray<FTransform>& Out)
{
	if (!Mesh)
	{
		return false;
	}
	const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
	FAnimationRuntime::FillUpComponentSpaceTransforms(Ref, Ref.GetRefBonePose(), Out);
	return Out.Num() > 0;
}

float UMorphRigEditorLibrary::AddOrUpdateSocket(USkeletalMesh* Mesh, FName SocketName, FName BoneName, FVector ComponentPosition, FVector ComponentForward, FVector ComponentUp)
{
#if WITH_EDITOR
	TArray<FTransform> CS;
	if (!ComponentSpaceRefPose(Mesh, CS))
	{
		return -1.f;
	}
	const int32 BoneIndex = Mesh->GetRefSkeleton().FindBoneIndex(BoneName);
	if (BoneIndex == INDEX_NONE)
	{
		UE_LOG(LogMorphRig, Error, TEXT("AddOrUpdateSocket: bone %s not found for socket %s"), *BoneName.ToString(), *SocketName.ToString());
		return -1.f;
	}
	// socket frame: X = forward, Z = up (re-orthogonalised), Y = Z x X (left handed)
	FVector X = ComponentForward.GetSafeNormal();
	FVector Z = (ComponentUp - X * FVector::DotProduct(ComponentUp, X)).GetSafeNormal();
	if (X.IsNearlyZero())
	{
		X = FVector::ForwardVector;
	}
	if (Z.IsNearlyZero())
	{
		Z = FVector::UpVector;
	}
	const FVector Y = FVector::CrossProduct(Z, X);
	const FTransform SocketCS(FRotationMatrix::MakeFromXZ(X, Z).ToQuat(), ComponentPosition);
	const FTransform Rel = SocketCS.GetRelativeTransform(CS[BoneIndex]);

	USkeletalMeshSocket* Socket = nullptr;
	for (USkeletalMeshSocket* S : Mesh->GetMeshOnlySocketList())
	{
		if (S && S->SocketName == SocketName)
		{
			Socket = S;
			break;
		}
	}
	Mesh->Modify();
	if (!Socket)
	{
		Socket = NewObject<USkeletalMeshSocket>(Mesh, NAME_None, RF_Transactional);
		Socket->SocketName = SocketName;
		Mesh->AddSocket(Socket, false);
	}
	Socket->BoneName = BoneName;
	Socket->RelativeLocation = Rel.GetLocation();
	Socket->RelativeRotation = Rel.GetRotation().Rotator();
	Socket->RelativeScale = FVector::OneVector;
	Mesh->MarkPackageDirty();
	const FTransform Check = FTransform(Socket->RelativeRotation, Socket->RelativeLocation) * CS[BoneIndex];
	return (float)FVector::Dist(Check.GetLocation(), ComponentPosition);
#else
	return -1.f;
#endif
}

void UMorphRigEditorLibrary::RemoveAllSockets(USkeletalMesh* Mesh)
{
#if WITH_EDITOR
	if (Mesh)
	{
		Mesh->Modify();
		Mesh->GetMeshOnlySocketList().Empty();
		Mesh->MarkPackageDirty();
	}
#endif
}

TArray<FString> UMorphRigEditorLibrary::DescribeNotifies(UAnimSequence* Sequence)
{
	TArray<FString> Out;
	if (Sequence)
	{
		for (const FAnimNotifyEvent& E : Sequence->Notifies)
		{
			const UMorphEventNotify* N = Cast<UMorphEventNotify>(E.Notify);
			Out.Add(FString::Printf(TEXT("%s@%.6f"), N ? *N->EventName.ToString() : *E.NotifyName.ToString(), E.GetTriggerTime()));
		}
	}
	return Out;
}

int32 UMorphRigEditorLibrary::GetLodTriangleCount(USkeletalMesh* Mesh, int32 LodIndex)
{
	if (Mesh)
	{
		if (const FSkeletalMeshRenderData* RD = Mesh->GetResourceForRendering())
		{
			if (RD->LODRenderData.IsValidIndex(LodIndex))
			{
				return RD->LODRenderData[LodIndex].GetTotalFaces();
			}
		}
	}
	return -1;
}

int32 UMorphRigEditorLibrary::GetLodMaxBoneInfluences(USkeletalMesh* Mesh, int32 LodIndex)
{
	if (Mesh)
	{
		if (const FSkeletalMeshRenderData* RD = Mesh->GetResourceForRendering())
		{
			if (RD->LODRenderData.IsValidIndex(LodIndex))
			{
				return (int32)RD->LODRenderData[LodIndex].GetVertexBufferMaxBoneInfluences();
			}
		}
	}
	return -1;
}

TArray<FName> UMorphRigEditorLibrary::GetRefBoneNames(USkeletalMesh* Mesh)
{
	TArray<FName> Out;
	if (Mesh)
	{
		const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
		for (int32 i = 0; i < Ref.GetNum(); ++i)
		{
			Out.Add(Ref.GetBoneName(i));
		}
	}
	return Out;
}

TArray<FVector> UMorphRigEditorLibrary::GetRefBoneComponentPositions(USkeletalMesh* Mesh)
{
	TArray<FVector> Out;
	TArray<FTransform> CS;
	if (ComponentSpaceRefPose(Mesh, CS))
	{
		for (const FTransform& T : CS)
		{
			Out.Add(T.GetLocation());
		}
	}
	return Out;
}

int32 UMorphRigEditorLibrary::MarkMorphCurves(USkeletalMesh* Mesh, const TArray<FName>& CurveNames)
{
	int32 Count = 0;
#if WITH_EDITOR
	USkeleton* Skeleton = Mesh ? Mesh->GetSkeleton() : nullptr;
	if (Skeleton)
	{
		Skeleton->Modify();
		for (const FName& N : CurveNames)
		{
			Skeleton->AddCurveMetaData(N, false);
			Skeleton->SetCurveMetaDataMorphTarget(N, true);
			++Count;
		}
		Skeleton->MarkPackageDirty();
	}
#endif
	return Count;
}

void UMorphRigEditorLibrary::SetLodScreenSizes(USkeletalMesh* Mesh, const TArray<float>& ScreenSizes)
{
#if WITH_EDITOR
	if (!Mesh)
	{
		return;
	}
	Mesh->Modify();
	for (int32 i = 0; i < ScreenSizes.Num() && i < Mesh->GetLODNum(); ++i)
	{
		if (FSkeletalMeshLODInfo* Info = Mesh->GetLODInfo(i))
		{
			Info->ScreenSize.Default = ScreenSizes[i];
			Info->LODHysteresis = 0.02f;
		}
	}
	Mesh->MarkPackageDirty();
#endif
}

float UMorphRigEditorLibrary::GetMorphTargetMaxDelta(USkeletalMesh* Mesh, FName MorphName, int32 LodIndex)
{
#if WITH_EDITOR
	if (!Mesh)
	{
		return -1.f;
	}
	for (UMorphTarget* MT : Mesh->GetMorphTargets())
	{
		if (MT && MT->GetFName() == MorphName)
		{
			float Max = 0.f;
			for (const FMorphTargetDelta& D : MT->GetMorphTargetDeltas(LodIndex))
			{
				Max = FMath::Max(Max, D.PositionDelta.Size());
			}
			return Max;
		}
	}
#endif
	return -1.f;
}

int32 UMorphRigEditorLibrary::GetMorphTargetVertexCount(USkeletalMesh* Mesh, FName MorphName, int32 LodIndex)
{
#if WITH_EDITOR
	if (Mesh)
	{
		for (UMorphTarget* MT : Mesh->GetMorphTargets())
		{
			if (MT && MT->GetFName() == MorphName)
			{
				return MT->GetMorphTargetDeltas(LodIndex).Num();
			}
		}
	}
#endif
	return -1;
}
