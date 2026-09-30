#include "MorphEditorTools.h"

#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Animation/Skeleton.h"

bool UMorphEditorTools::AddSocket(USkeletalMesh* Mesh, FName Socket, FName Bone)
{
	if (!Mesh || !Mesh->GetSkeleton())
	{
		return false;
	}
	USkeleton* Skel = Mesh->GetSkeleton();
	for (USkeletalMeshSocket* S : Skel->Sockets)
	{
		if (S && S->SocketName == Socket)
		{
			S->BoneName = Bone;
			S->RelativeLocation = FVector::ZeroVector;
			S->RelativeRotation = FRotator::ZeroRotator;
			Skel->MarkPackageDirty();
			return true;
		}
	}
	USkeletalMeshSocket* S = NewObject<USkeletalMeshSocket>(Skel);
	S->SocketName = Socket;
	S->BoneName = Bone;
	Skel->Modify();
	Skel->Sockets.Add(S);
	Skel->MarkPackageDirty();
	return true;
}

int32 UMorphEditorTools::SetLODScreenSizes(USkeletalMesh* Mesh, const TArray<float>& Sizes)
{
	if (!Mesh)
	{
		return 0;
	}
	int32 N = 0;
	for (int32 i = 0; i < Sizes.Num() && i < Mesh->GetLODNum(); ++i)
	{
		if (FSkeletalMeshLODInfo* Info = Mesh->GetLODInfo(i))
		{
			Info->ScreenSize = Sizes[i];
			++N;
		}
	}
	Mesh->MarkPackageDirty();
	return N;
}
