#include "OperativeLibrary.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Engine/World.h"
#include "Algo/Reverse.h"

float FOperativeClipInfo::Length() const
{
	return Sequence ? Sequence->GetPlayLength() : DurationS;
}

namespace
{
	FString LibJsonScalarToString(const TSharedPtr<FJsonValue>& V)
	{
		if (!V.IsValid()) return FString();
		switch (V->Type)
		{
		case EJson::String: return V->AsString();
		case EJson::Number: { const double N = V->AsNumber(); return FMath::IsNearlyEqual(N, FMath::RoundToDouble(N)) ? FString::Printf(TEXT("%d"), (int32)FMath::RoundToDouble(N)) : FString::SanitizeFloat(N); }
		case EJson::Boolean: return V->AsBool() ? TEXT("true") : TEXT("false");
		default: return FString();
		}
	}

	TSharedPtr<FJsonObject> LibParseObject(const FString& Json)
	{
		TSharedPtr<FJsonObject> Root;
		if (Json.IsEmpty()) return Root;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
		if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
		{
			UE_LOG(LogMorphRig, Error, TEXT("OperativeLibrary: JSON parse failed"));
			Root.Reset();
		}
		return Root;
	}
}

bool UOperativeLibrary::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	return World && World->IsGameWorld();
}

UOperativeLibrary* UOperativeLibrary::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UOperativeLibrary>() : nullptr;
}

void UOperativeLibrary::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	Assets = LoadObject<UOperativeAssets>(nullptr, TEXT("/Game/Operative/DA_OperativeAssets.DA_OperativeAssets"));
	if (!Assets)
	{
		UE_LOG(LogMorphRig, Error, TEXT("OperativeLibrary: /Game/Operative/DA_OperativeAssets missing. Run tools/ue_import_all.sh."));
		return;
	}
	ParseManifest(Assets->ManifestJson);
	ParseSockets(Assets->SocketsJson);
	ParseAlignment(Assets->AlignmentJson);
	// resolve sequences by asset name (= clip id)
	int32 Resolved = 0;
	for (UAnimSequence* Seq : Assets->Clips)
	{
		if (!Seq) continue;
		if (FOperativeClipInfo* Info = Clips.Find(Seq->GetFName()))
		{
			Info->Sequence = Seq;
			++Resolved;
		}
	}
	BuildBoneChains();
	bReady = Clips.Num() > 0;
	UE_LOG(LogMorphRig, Log, TEXT("OperativeLibrary: %s"), *GetSummary());
	if (Resolved != Clips.Num())
	{
		UE_LOG(LogMorphRig, Warning, TEXT("OperativeLibrary: %d of %d manifest clips have an imported AnimSequence"), Resolved, Clips.Num());
	}
}

void UOperativeLibrary::ParseManifest(const FString& Json)
{
	Clips.Reset();
	ClipOrder.Reset();
	TSharedPtr<FJsonObject> Root = LibParseObject(Json);
	if (!Root.IsValid()) return;
	const TArray<TSharedPtr<FJsonValue>>* ClipArr = nullptr;
	if (!Root->TryGetArrayField(TEXT("clips"), ClipArr)) return;
	for (const TSharedPtr<FJsonValue>& CV : *ClipArr)
	{
		const TSharedPtr<FJsonObject> C = CV->AsObject();
		if (!C.IsValid()) continue;
		FOperativeClipInfo Info;
		FString S;
		C->TryGetStringField(TEXT("id"), S);
		if (S.IsEmpty()) continue;
		Info.Id = FName(*S);
		C->TryGetStringField(TEXT("form"), Info.Form);
		C->TryGetStringField(TEXT("behavior"), Info.Behavior);
		FString LayerStr;
		C->TryGetStringField(TEXT("layer"), LayerStr);
		Info.Layer = FName(*LayerStr);
		FString Root2;
		C->TryGetStringField(TEXT("root_motion"), Root2);
		Info.bRootMotion = (Root2 == TEXT("root_motion"));
		C->TryGetBoolField(TEXT("loop"), Info.bLoop);
		C->TryGetBoolField(TEXT("static_pose"), Info.bStaticPose);
		C->TryGetBoolField(TEXT("additive"), Info.bAdditive);
		double D = 0;
		if (C->TryGetNumberField(TEXT("frames"), D)) Info.Frames = (int32)D;
		if (C->TryGetNumberField(TEXT("duration_s"), D)) Info.DurationS = (float)D;
		if (C->TryGetNumberField(TEXT("nominal_speed_cm_s"), D)) Info.NominalSpeed = (float)D;
		const TSharedPtr<FJsonObject>* RM = nullptr;
		if (C->TryGetObjectField(TEXT("root_motion_cm"), RM))
		{
			double X = 0, Y = 0, Z = 0;
			(*RM)->TryGetNumberField(TEXT("x"), X);
			(*RM)->TryGetNumberField(TEXT("y"), Y);
			(*RM)->TryGetNumberField(TEXT("z"), Z);
			Info.RootMotionCm = FVector(X, Y, Z);
		}
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (C->TryGetArrayField(TEXT("events"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& EV : *Arr)
			{
				const TSharedPtr<FJsonObject> E = EV->AsObject();
				if (!E.IsValid()) continue;
				FOperativeEventDef Def;
				FString N;
				E->TryGetStringField(TEXT("name"), N);
				if (N.IsEmpty()) continue;
				Def.Name = FName(*N);
				double Fr = 0, T = -1;
				E->TryGetNumberField(TEXT("frame"), Fr);
				Def.Frame = (int32)Fr;
				Def.TimeS = E->TryGetNumberField(TEXT("time_s"), T) ? (float)T : (float)(Fr / 30.0);
				const TSharedPtr<FJsonObject>* P = nullptr;
				if (E->TryGetObjectField(TEXT("params"), P))
				{
					for (const auto& KV : (*P)->Values)
					{
						const FString Key = FString(KV.Key);
						Def.Params.Add(FName(*Key), LibJsonScalarToString(KV.Value));
					}
				}
				Info.Events.Add(Def);
			}
			Info.Events.StableSort([](const FOperativeEventDef& A, const FOperativeEventDef& B) { return A.TimeS < B.TimeS; });
		}
		if (C->TryGetArrayField(TEXT("foot_contacts"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& FV : *Arr)
			{
				FOperativeFootContact FC;
				if (const TArray<TSharedPtr<FJsonValue>>* Tup = nullptr; FV->TryGetArray(Tup) && Tup->Num() >= 3)
				{
					FC.Frame = (int32)(*Tup)[0]->AsNumber();
					FC.Foot = FName(*(*Tup)[1]->AsString());
					FC.bPlant = (*Tup)[2]->AsString() == TEXT("plant");
				}
				else if (const TSharedPtr<FJsonObject> O = FV->AsObject(); O.IsValid())
				{
					double Fr = 0;
					O->TryGetNumberField(TEXT("frame"), Fr);
					FC.Frame = (int32)Fr;
					FString Foot, Kind;
					O->TryGetStringField(TEXT("foot"), Foot);
					if (!O->TryGetStringField(TEXT("kind"), Kind)) O->TryGetStringField(TEXT("type"), Kind);
					FC.Foot = FName(*Foot);
					FC.bPlant = Kind != TEXT("lift");
				}
				else
				{
					continue;
				}
				Info.FootContacts.Add(FC);
			}
		}
		const TSharedPtr<FJsonObject>* MetaObj = nullptr;
		if (C->TryGetObjectField(TEXT("procedural_components"), MetaObj))
		{
			for (const auto& KV : (*MetaObj)->Values)
			{
				const FString Key = FString(KV.Key);
				Info.Meta.Add(FName(*Key), LibJsonScalarToString(KV.Value));
			}
		}
		if (C->TryGetArrayField(TEXT("morph_curves"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& MV : *Arr) Info.MorphCurves.Add(FName(*MV->AsString()));
		}
		if (C->TryGetArrayField(TEXT("entry_states"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& MV : *Arr) Info.EntryStates.Add(MV->AsString());
		}
		if (C->TryGetArrayField(TEXT("exit_states"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& MV : *Arr) Info.ExitStates.Add(MV->AsString());
		}
		ClipOrder.Add(Info.Id);
		Clips.Add(Info.Id, MoveTemp(Info));
	}
}

void UOperativeLibrary::ParseSockets(const FString& Json)
{
	MorphNames.Reset();
	Visemes.Reset();
	TSharedPtr<FJsonObject> Root = LibParseObject(Json);
	if (!Root.IsValid()) return;
	const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
	if (Root->TryGetArrayField(TEXT("morph_targets"), Arr))
	{
		for (const TSharedPtr<FJsonValue>& V : *Arr)
		{
			if (MorphNames.Num() < OPERATIVE_MAX_MORPHS) MorphNames.Add(FName(*V->AsString()));
		}
	}
	const TSharedPtr<FJsonObject>* VObj = nullptr;
	if (Root->TryGetObjectField(TEXT("visemes"), VObj))
	{
		for (const auto& KV : (*VObj)->Values)
		{
			const TSharedPtr<FJsonObject> O = KV.Value->AsObject();
			if (!O.IsValid()) continue;
			FOperativeViseme V;
			const FString VisemeName = FString(KV.Key);
			V.Name = FName(*VisemeName);
			double D = 0;
			if (O->TryGetNumberField(TEXT("jaw_open"), D)) V.JawOpen = (float)D;
			if (O->TryGetNumberField(TEXT("tongue"), D)) V.Tongue = (float)D;
			O->TryGetStringField(TEXT("phonemes"), V.Phonemes);
			const TSharedPtr<FJsonObject>* Morphs = nullptr;
			if (O->TryGetObjectField(TEXT("morphs"), Morphs))
			{
				for (const auto& MKV : (*Morphs)->Values)
				{
					const FString MorphKey = FString(MKV.Key);
					const int32 Idx = MorphNames.IndexOfByKey(FName(*MorphKey));
					if (Idx != INDEX_NONE) V.Morphs.Emplace(Idx, (float)MKV.Value->AsNumber());
				}
			}
			if (Visemes.Num() < OPERATIVE_MAX_VISEMES) Visemes.Add(MoveTemp(V));
		}
	}
}

void UOperativeLibrary::ParseAlignment(const FString& Json)
{
	SpeechWords.Reset();
	SpeechSentences.Reset();
	TSharedPtr<FJsonObject> Root = LibParseObject(Json);
	if (!Root.IsValid()) return;
	auto Read = [](const TArray<TSharedPtr<FJsonValue>>& Arr, TArray<FOperativeSpeechSpan>& Out)
	{
		for (const TSharedPtr<FJsonValue>& V : Arr)
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid()) continue;
			FOperativeSpeechSpan S;
			O->TryGetStringField(TEXT("text"), S.Text);
			double D = 0;
			if (O->TryGetNumberField(TEXT("start"), D)) S.Start = (float)D;
			if (O->TryGetNumberField(TEXT("end"), D)) S.End = (float)D;
			if (O->TryGetNumberField(TEXT("sentence"), D)) S.Sentence = (int32)D;
			Out.Add(S);
		}
	};
	const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
	if (Root->TryGetArrayField(TEXT("words"), Arr)) Read(*Arr, SpeechWords);
	if (Root->TryGetArrayField(TEXT("sentences"), Arr)) Read(*Arr, SpeechSentences);
	for (int32 I = 0; I < SpeechSentences.Num(); ++I) SpeechSentences[I].Sentence = I;
}

void UOperativeLibrary::BuildBoneChains()
{
	bChainsValid = false;
	LeftChain.Reset();
	RightChain.Reset();
	const FOperativeClipInfo* Any = nullptr;
	for (const TPair<FName, FOperativeClipInfo>& KV : Clips)
	{
		if (KV.Value.Sequence) { Any = &KV.Value; break; }
	}
	if (!Any) return;
	const USkeleton* Skel = Any->Sequence->GetSkeleton();
	if (!Skel) return;
	const FReferenceSkeleton& Ref = Skel->GetReferenceSkeleton();
	static const TCHAR* LeftNames[] = { TEXT("root"), TEXT("pelvis"), TEXT("thigh_l"), TEXT("calf_l"), TEXT("foot_l") };
	static const TCHAR* RightNames[] = { TEXT("root"), TEXT("pelvis"), TEXT("thigh_r"), TEXT("calf_r"), TEXT("foot_r") };
	for (const TCHAR* N : LeftNames) { const int32 I = Ref.FindBoneIndex(FName(N)); if (I == INDEX_NONE) return; LeftChain.Add(I); }
	for (const TCHAR* N : RightNames) { const int32 I = Ref.FindBoneIndex(FName(N)); if (I == INDEX_NONE) return; RightChain.Add(I); }
	bChainsValid = true;
}

UAnimSequence* UOperativeLibrary::GetSequence(FName Id) const
{
	const FOperativeClipInfo* Info = Clips.Find(Id);
	return Info ? Info->Sequence : nullptr;
}

float UOperativeLibrary::GetClipLength(FName Id) const
{
	const FOperativeClipInfo* Info = Clips.Find(Id);
	return Info ? Info->Length() : 0.f;
}

int32 UOperativeLibrary::FindMorphIndex(FName Name) const
{
	return MorphNames.IndexOfByKey(Name);
}

int32 UOperativeLibrary::FindViseme(FName Name) const
{
	return Visemes.IndexOfByPredicate([Name](const FOperativeViseme& V) { return V.Name == Name; });
}

const TArray<FOperativeEventDef>* UOperativeLibrary::GetEvents(FName ClipId) const
{
	const FOperativeClipInfo* Info = Clips.Find(ClipId);
	return Info ? &Info->Events : nullptr;
}

bool UOperativeLibrary::GetFootPositions(FName ClipId, float Time, FVector& OutLeft, FVector& OutRight) const
{
	const FOperativeClipInfo* Info = Clips.Find(ClipId);
	if (!Info || !Info->Sequence || !bChainsValid) return false;
	const FAnimExtractContext Ctx(FMath::Clamp((double)Time, 0.0, (double)Info->Sequence->GetPlayLength()), false);
	auto Solve = [&](const TArray<int32>& Chain) -> FVector
	{
		FTransform Acc = FTransform::Identity;
		for (const int32 Bone : Chain)
		{
			FTransform Local;
			Info->Sequence->GetBoneTransform(Local, FSkeletonPoseBoneIndex(Bone), Ctx, false);
			Acc = Local * Acc;
		}
		return Acc.GetLocation();
	};
	OutLeft = Solve(LeftChain);
	OutRight = Solve(RightChain);
	return true;
}

bool UOperativeLibrary::GetBonePositionCS(FName ClipId, FName BoneName, float Time, FVector& OutPos) const
{
	const FOperativeClipInfo* Info = Clips.Find(ClipId);
	if (!Info || !Info->Sequence) return false;
	const TArray<int32>* Chain = BoneChainCache.Find(BoneName);
	if (!Chain)
	{
		const USkeleton* Skel = Info->Sequence->GetSkeleton();
		if (!Skel) return false;
		const FReferenceSkeleton& Ref = Skel->GetReferenceSkeleton();
		int32 B = Ref.FindBoneIndex(BoneName);
		if (B == INDEX_NONE) return false;
		TArray<int32> Up;
		while (B != INDEX_NONE) { Up.Add(B); B = Ref.GetParentIndex(B); }
		Algo::Reverse(Up);
		Chain = &BoneChainCache.Add(BoneName, MoveTemp(Up));
	}
	const FAnimExtractContext Ctx(FMath::Clamp((double)Time, 0.0, (double)Info->Sequence->GetPlayLength()), false);
	FTransform Acc = FTransform::Identity;
	for (const int32 Bone : *Chain)
	{
		FTransform Local;
		Info->Sequence->GetBoneTransform(Local, FSkeletonPoseBoneIndex(Bone), Ctx, false);
		Acc = Local * Acc;
	}
	OutPos = Acc.GetLocation();
	return true;
}

float UOperativeLibrary::MatchLoopPhase(FName ClipId, const FVector& RefLeft, const FVector& RefRight, int32 Steps) const
{
	const FOperativeClipInfo* Info = Clips.Find(ClipId);
	if (!Info || !Info->Sequence || Steps < 2) return 0.f;
	const float Len = Info->Sequence->GetPlayLength();
	float BestPhase = 0.f, BestErr = TNumericLimits<float>::Max();
	for (int32 K = 0; K < Steps; ++K)
	{
		const float Phase = (float)K / (float)Steps;
		FVector L, R;
		if (!GetFootPositions(ClipId, Phase * Len, L, R)) return 0.f;
		// compare in the horizontal plane weighted with height (ankle height distinguishes contact from swing)
		const float Err = FVector::Dist(L, RefLeft) + FVector::Dist(R, RefRight);
		if (Err < BestErr) { BestErr = Err; BestPhase = Phase; }
	}
	return BestPhase;
}

FString UOperativeLibrary::GetSummary() const
{
	int32 WithEvents = 0, Loops = 0, WithSeq = 0;
	for (const TPair<FName, FOperativeClipInfo>& KV : Clips)
	{
		WithEvents += KV.Value.Events.Num() > 0 ? 1 : 0;
		Loops += KV.Value.bLoop ? 1 : 0;
		WithSeq += KV.Value.Sequence ? 1 : 0;
	}
	return FString::Printf(TEXT("clips=%d sequences=%d loops=%d clips_with_events=%d morphs=%d visemes=%d stamp=%s"),
		Clips.Num(), WithSeq, Loops, WithEvents, MorphNames.Num(), Visemes.Num(), Assets ? *Assets->ImportStamp : TEXT("-"));
}
