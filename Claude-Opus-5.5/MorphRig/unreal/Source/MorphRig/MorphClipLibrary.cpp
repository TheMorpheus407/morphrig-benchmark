#include "MorphClipLibrary.h"

#include "Animation/AnimSequence.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "MorphEventNotify.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogMorphClips, Log, All);

bool UMorphClipLibrary::Load()
{
	Clips.Reset();
	Index.Reset();
	Loaded.Reset();
	const FString Path = FPaths::ProjectContentDir() / TEXT("MorphRig/Data/clips.json");
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		UE_LOG(LogMorphClips, Error, TEXT("clip table not found: %s"), *Path);
		return false;
	}
	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogMorphClips, Error, TEXT("clip table is not valid JSON"));
		return false;
	}
	for (const TSharedPtr<FJsonValue>& V : Root->GetArrayField(TEXT("clips")))
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FMorphClip C;
		C.Id = FName(*O->GetStringField(TEXT("id")));
		const FString Asset = O->GetStringField(TEXT("asset"));
		C.Seq = LoadObject<UAnimSequence>(nullptr, *Asset);
		if (!C.Seq)
		{
			UE_LOG(LogMorphClips, Warning, TEXT("missing sequence %s"), *Asset);
			continue;
		}
		Loaded.Add(C.Seq);
		C.Frames = O->GetIntegerField(TEXT("frames"));
		C.Duration = C.Seq->GetPlayLength();
		C.bLoop = O->GetBoolField(TEXT("loop"));
		C.Form = O->GetStringField(TEXT("form"));
		C.Root = O->GetStringField(TEXT("root"));
		C.Layer = O->GetStringField(TEXT("layer"));
		C.SpeedCms = (float)O->GetNumberField(TEXT("speed_cms"));
		C.Entry = O->GetStringField(TEXT("entry"));
		C.Exit = O->GetStringField(TEXT("exit"));
		C.Notes = O->GetStringField(TEXT("notes"));
		O->TryGetStringField(TEXT("behavior"), C.Behavior);
		O->TryGetBoolField(TEXT("required"), C.bRequired);
		C.bAdditive = C.Seq->IsValidAdditive();
		C.bRootMotion = C.Seq->bEnableRootMotion;
		for (const FAnimNotifyEvent& N : C.Seq->Notifies)
		{
			if (const UMorphEventNotify* E = Cast<UMorphEventNotify>(N.Notify))
			{
				C.Markers.Add({N.GetTriggerTime(), E->EventName});
			}
		}
		C.Markers.Sort([](const FMorphMarker& A, const FMorphMarker& B) { return A.Time < B.Time; });
		Index.Add(C.Id, Clips.Num());
		Clips.Add(MoveTemp(C));
	}
	UE_LOG(LogMorphClips, Log, TEXT("loaded %d clips (%d inventory entries)"), Clips.Num(), NumRequired());
	return Clips.Num() > 0;
}

const FMorphClip* UMorphClipLibrary::Find(FName Id) const
{
	const int32* I = Index.Find(Id);
	return I ? &Clips[*I] : nullptr;
}

int32 UMorphClipLibrary::NumRequired() const
{
	int32 N = 0;
	for (const FMorphClip& C : Clips)
	{
		N += C.bRequired ? 1 : 0;
	}
	return N;
}
